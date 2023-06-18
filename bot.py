import logging # Per loggare (non si usa "print()" ma logger.info())

from string import capwords
from typing import Dict
from time import sleep
import requests

import gettext
import users


from telegram.ext import (
    Application, # Per il bot
    CommandHandler, # Per i comandi
    MessageHandler, # Per i messaggi
    ConversationHandler, # Per più handler concatenati (Può salvare il suo stato con PicklePersistance)
    ContextTypes, # Per avere il tipo di context (ContextTypes.DEFAULT)
    CallbackQueryHandler, # Per gestire il click di un bottone o simile
    filters, # Per filtrare gli Handler 
    PicklePersistence, # Per un ConversationHandler, vedi https://gist.github.com/aahnik/6c9dd519c61e718e4da5f0645aa11ada#file-tg_conv_bot-py-L9t
    ExtBot
)

import telegram
from telegram import (
    ChatMemberAdministrator,
    ChatMemberOwner,
    Update, # È il tipo che usiamo nei parametri dei metodi
    User, # Tipo che rappresenta un Utente
    Message, # Tipo che rappresenta un Messaggio
    InlineKeyboardButton, # Per le tastiere
    InlineKeyboardMarkup, # Per le tastiere
    
)

from telegram.constants import (
    ParseMode, # Per assegnare il parametro "parse_mode=" nei messaggi che il bot invia
    ChatMemberStatus
)


TOKEN = None  # TOKEN DEL BOT
with open('token.txt', 'r') as f:
    TOKEN = f.read().strip()

# ID TELEGRAM PER RICEVERE NOTIFICA (ottienilo con t.me/JsonDumpBot)
MASTER_ADMIN = ["245996916"]
ID_CANALE_LOG = '-1001741378490'

# https://docs.python-telegram-bot.org/en/stable/telegram.ext.handler.html

# Questa è la configurazione di base del log, io lo lascio così di solito
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)

_ = gettext.gettext

# Rappresenta un partecipante alla partita:
#   nomeUtente: Il suo username o nome e cognome
#   idUtente: Il suo id
#   hasWritten: Se ha già scritto una parola o no
class Partecipante:
    def __init__(self, username, id) -> None:
        self.nomeUtente = username
        self.idUtente: str = str(id)
        self.hasWritten = False
        self.voteSkip = False


# Rappresenta una partita:
#   leader: Nome utente del leader
#   leaderId: Id del leader
#   partecipanti: Dictionary [id utente, classe "Partecipante"]
#   isStarted: Se la partita è avviata o no
#   MessaggioListaPartecipanti: Il messaggio dove verrà aggiornata la lista dei partecipanti
#   
#   Per tutti i metodi basta leggere il nome del metodo
#   per getAllPartecipants se metti (True) ti restituisce la lista dei nomi dei partecipanti sotto forma di stringa (con a capo per ogni utente)
class Partita:
    def __init__(self, utente, userId, mess) -> None:
        self.leader: str = utente
        self.leaderId: str = str(userId)
        self.partecipanti: Dict[str, Partecipante] = {}
        self.isStarted: bool = False
        self.MessaggioListaPartecipanti: Message = mess
        self.MessaggioVoteSkip: Message = None
        self.storia: list[Message] = []
        self.skipping: bool = False
        self.nonsocomechiamarequestavariabile: dict[str,Message] = {}
        self.timer = 150

    def getAllPartecipantsIDs(self) -> list[str]:
        return list(self.partecipanti.keys())

    def getAllPartecipants(self) -> list[Partecipante]:
        return list(self.partecipanti.values())
    
    def getNumberOfPlayers(self) -> int:
        return len(list(self.getAllPartecipantsIDs()))

    def getAllPartecipantsString(self) -> str:
        listaStringa = ''
        
        for partecipante in self.getAllPartecipants():
            listaStringa += '- ' + partecipante.nomeUtente + '\n'
        
        return listaStringa

    def prossimoTurno(self) -> Partecipante:
        for partecipante in self.getAllPartecipantsIDs():
            if not self.partecipanti[partecipante].hasWritten:
                return self.partecipanti[partecipante]
        if not self.getAllPartecipants()[0].hasWritten:
            return self.getAllPartecipants()[0]

    def getVotes(self):
        voti: int = 0
        for partecipante in self.getAllPartecipants():
            if partecipante.voteSkip:
                voti += 1
        return voti
    
    def resetVotes(self):
        for partecipante in self.getAllPartecipants():
            partecipante.voteSkip = False
    
    def ottieniStoria(self, parole=-1):
        if parole <= 0:
            return " ".join([formattaMessaggio(k.text) for k in self.storia])
        return " ".join([formattaMessaggio(k.text) for k in self.storia[parole*-1:]])
    
    def everyone_has_written(self):
        for partecipante in self.getAllPartecipants():
            if not partecipante.hasWritten:
                return False
        return True
    
    def lastWordOf(self,userId: str | int):
        for word in self.storia[::-1]:
            if str(word.from_user.id) == str(userId):
                return word
            
    def timer_working(self):
        while True:
            self.timer -= 1
            sleep(1)
            
    def reset_timer(self):
        self.timer = 150
            

def formattaMessaggio(text):
    return text[1:]

#        group_id: Partita
partite: Dict[str, Partita] = {}

# #       group_id: storia
# storie: Dict[str, str] = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):  # /start
    
    utente = ('@' + update.message.from_user.username) if update.message.from_user.username != None else update.message.from_user.full_name
    idUtente = update.message.from_user.id

    users.saveUser(str(idUtente), utente, update.message.from_user.language_code)
    cambiaLingua(str(idUtente),users.getUserLang(str(idUtente)))

    logging.info(f'{utente}, {idUtente} - Ha eseguito /start')
    await prova_messaggio(_(
        'Benvenuto nel bot "One Word Story". Per giocare aggiungimi in un gruppo e fai /crea_partita'),
                    update=update,
                    bot=context.bot)


async def prova_messaggio(messaggio:str, update: Update, bot: ExtBot, parse_mode=ParseMode.HTML, reply_markup=None):
    
    try: 
        return await update.effective_message.reply_text(
            messaggio, 
            parse_mode=parse_mode,
            reply_markup=reply_markup
        )
    except:
        return await bot.send_message(
            chat_id = update.effective_message.chat_id,
            text = messaggio,
            parse_mode = parse_mode,
            reply_markup=reply_markup
        )

async def crea_partita(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global partite

    roba = update.message if update.message is not None else update.edited_message

    # Assegno tutte le variabili per comodità
    utente = roba.from_user.name
    idUtente = str(roba.from_user.id)
    chat_id = roba.chat.id

    cambiaLingua(str(idUtente),users.getUserLang(str(idUtente)))

    # Controllo se la chat è una chat privata, se sì esce dalla funzione
    if chat_id > 0:
        await prova_messaggio(_(
            'Hey {utente}, non vorrai mica giocare da solo? Usa questo comando in un gruppo').format(utente=utente),update=update,
                    bot=context.bot)
        return

    # Se la chat non è presente nella lista delle partite
    if not f'{chat_id}' in partite:
        
        mess = await prova_messaggio(_(
            '{utente} ha creato una partita. Entra con /join_ows_game.\n\nPartecipanti:\n- {utente}').format(utente=utente),update=update,
                    bot=context.bot)
        
        partite[f'{chat_id}'] = Partita(utente, idUtente, mess=mess) # Crea la partita con l'utente leader (chi l'ha creata)
        
        partite[f'{chat_id}'].partecipanti[f'{idUtente}'] = Partecipante(utente, idUtente) # Aggiungo il creatore ai partecipanti
        
        if (await update.message.chat.get_member(context.bot.id)) != ChatMemberStatus.ADMINISTRATOR:
            await prova_messaggio(_('Il bot non ha i permessi per cancellare i messaggi, si può giocare comunque, ma consiglio di darglieli.'),update=update,
                    bot=context.bot)

        logging.info(f'{utente}, {idUtente} - Ha creato una partita nel gruppo {update.message.chat.title}')
    else: # Avviso se la partita è già presente nella lista
        await prova_messaggio(_(
            'Partita già creata. Entra con /join_ows_game'),update=update,
                    bot=context.bot)

def gameExists(chat_id: int):
    return str(chat_id) in partite

async def join_ows_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global partite


    roba = update.message if update.message is not None else update.edited_message
    
    # Assegno tutte le variabili per comodità
    # "utente" fa il controllo se l'username è presente altrimenti usa il nome
    utente = roba.from_user.name
    idUtente = str(update.message.from_user.id)
    chat_id = update.message.chat.id

    cambiaLingua(idUtente,users.getUserLang(idUtente))

    # Controllo se per la chat esiste una partita
    if not gameExists(chat_id):
        await prova_messaggio(
            _('Non è stata creata nessuna partita. Creane una con /crea_partita'),
            update=update,
            bot=context.bot
        )
        return
    partita = partite[f'{chat_id}']
    
    # Controllo se l'utente è già nella lista dei partecipanti della partita
    if idUtente in partita.partecipanti:
        await prova_messaggio(
            _('Partecipi già alla partita!'),
            update=update,
            bot=context.bot
        )
        return

    # Creo il nuovo partecipante
    partite[f'{chat_id}'].partecipanti[f'{idUtente}'] = Partecipante(utente, idUtente)
    
    # Modifica il messaggio di creazione della partita per mostrare la lista dei partecipanti al game
    try:
        partite[f'{chat_id}'].MessaggioListaPartecipanti = await context.bot.edit_message_text(
            chat_id = chat_id, 
            message_id = partita.MessaggioListaPartecipanti.message_id, 
            text = partita.MessaggioListaPartecipanti.text + f"\n- {utente}"
        )
    except:
        await prova_messaggio(
            partita.MessaggioListaPartecipanti.text + f"\n- {utente}",
            update=update,
            bot=context.bot
        )
    await prova_messaggio(
        _('{user} è entrato nella partita').format(user=utente),
        update=update,
        bot=context.bot
    )

async def avvia_partita(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global partite

    roba = update.message if update.message is not None else update.edited_message

    # Solite variabili per comodità
    utente = roba.from_user.name
    idUtente = str(roba.from_user.id)
    chat_id = roba.chat.id
    
    cambiaLingua(str(idUtente),users.getUserLang(str(idUtente)))
    
    # Se la partita non esiste
    if not gameExists(chat_id): 
        await prova_messaggio(
            _('Non è stata creata nessuna partita. Creane una con /crea_partita'),
            update=update,
            bot=context.bot
        )
        return
    
    partita = partite[f"{chat_id}"]
    
    # Controlla se la partita è già avviata
    if partita.isStarted:
        await prova_messaggio(
            _("Partita già avviata"),
            update=update,
            bot=context.bot
        )
        return
    
    # Se un utente che non è il creatore prova ad avviare la partita, non può
    if not idUtente == partita.leaderId:
        await prova_messaggio(
            _("Solo il creatore della partita ({creator}) può avviarla.").format(creator=partita.leader),
            update=update,
            bot=context.bot
        )
        return

    # Se tutti i controlli sono andati a buon fine, avvia la partita
    partita.isStarted = True 
    await prova_messaggio(
        _("{utente} ha avviato la partita. Prenderò una parola a testa da ognuno di voi in ordine, per poi comporre una storia da esse.\n\nL'ordine dei turni è:\n{turns}").format(utente = utente, turns = partita.getAllPartecipantsString()),
        update=update,
        bot=context.bot
    )
    partita.MessaggioListaPartecipanti = None
    context.job_queue.run_once(callback=test, when=50, data=(partita,update),name=f"{partita.prossimoTurno().idUtente}")
    

async def onMessageInGroup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global partite

    roba = update.effective_message
    
    chat_id = roba.chat_id
    utente = roba.from_user.name
    idUtente = str(roba.from_user.id)
    messaggio_id = roba.message_id


    # Se la partita non esiste o non è stata avviata non fare nulla
    if (not f'{chat_id}' in partite):
        return

    partita = partite[f"{chat_id}"]

    if not partita.isStarted:
        return
    
    # Se l'utente non è in partita, non fare nulla
    if not str(idUtente) in partita.getAllPartecipantsIDs():
        return
    
    cambiaLingua(idUtente,users.getUserLang(idUtente))


    
    # Se il messaggio è modificato, non aggiornare la storia
    if update.edited_message != None:
        await prova_messaggio(
            _('Hey {user}, non puoi modificare un messaggio! La tua parola rimarrà {word}.').format(
                user=utente,
                word=formattaMessaggio(partita.lastWordOf(idUtente).text)
            ),
            update=update, 
            bot=context.bot
        )
        return

    messaggio = roba.text 

    # Caratteri per far considerare i messaggi dal bot
    if not (messaggio[0:1] == '*'):
        return
    
    messaggio = formattaMessaggio(messaggio)
    
    # Se non è il turno dell'utente avvisa e cancella il messaggio
    if not idUtente == partita.prossimoTurno().idUtente:
        messaggioDaCancellare = await prova_messaggio(
            _("{utente}, non è il tuo turno. Tocca a {turno}").format(utente=utente, turno=partita.prossimoTurno().nomeUtente),
            update=update,
            bot=context.bot
        )
        
        try:
            await context.bot.delete_message(chat_id, messaggio_id)
        except:
            pass
        
        sleep(3)
        await messaggioDaCancellare.delete()
        return
    
    

    # Se il messaggio contiene uno dei seguenti caratteri avvisa e cancella il messaggio
    if (' ' in messaggio or '_' in messaggio or '-' in messaggio or '+' in messaggio):
        messaggioDaCancellare = await prova_messaggio(
            _('{utente}, devi scrivere una parola sola :P\nil gioco si chiama "ONE WORD stories" per un motivo.').format(utente=utente),
            update=update,
            bot=context.bot
        )
        
        try:
            await context.bot.delete_message(chat_id, messaggio_id)
        except:
            pass

        sleep(3)
        await messaggioDaCancellare.delete()
        return

    max_caratteri = 15

    # Se il messaggio è troppo lungo avvia e cancella il messaggio
    if (len(messaggio) > max_caratteri):
        messaggioDaCancellare = await prova_messaggio(_(
            '{user}, il messaggio è troppo lungo (più di {max_length})').format(user=utente, max_length=max_caratteri),
            update=update,
            bot=context.bot
        )
        try:
            await context.bot.delete_message(chat_id, messaggio_id)
        except:
            pass
        
        sleep(3)
        await context.bot.delete_message(chat_id, messaggioDaCancellare.message_id)
        
        return

    partecipante = partita.partecipanti[idUtente]

    
    
    # Se il partecipante ha già scritto avvisa e cancella il messaggio
    if partecipante.hasWritten:
        messaggioDaCancellare = await prova_messaggio(
            _('{user} hai già scritto una parola.').format(user=utente),
            update=update,
            bot=context.bot
        )
        
        # Controllo che il bot possa cancellare i messaggi
        try:
            await context.bot.delete_message(chat_id, messaggio_id)
        except:
            pass
        
        sleep(3)
        await messaggioDaCancellare.delete()
        return

    if idUtente in partita.nonsocomechiamarequestavariabile:
        await partita.nonsocomechiamarequestavariabile[idUtente].delete()
        partita.nonsocomechiamarequestavariabile.pop(idUtente)
        
    current_jobs = context.job_queue.get_jobs_by_name(f"{roba.chat.id} - {idUtente}")
    if current_jobs:
        for job in current_jobs:
            job.schedule_removal()

    partita.storia.append(update.effective_message)
    partecipante.hasWritten = True

    if partita.everyone_has_written():
        for partecipante in partita.getAllPartecipants():
            partecipante.hasWritten = False
        
        context.job_queue.run_once(callback=test, when=50, data=(partita,update),name=f"{partita.prossimoTurno().idUtente}")
        
        messaggioDaCancellare = await prova_messaggio(
            _('Tutti i partecipanti hanno scritto una parola. Ora ricominciamo da {user}').format(user=partita.prossimoTurno().nomeUtente),
            update=update,
            bot=context.bot
        )
        
        sleep(3)
        await messaggioDaCancellare.delete()
        return

    context.job_queue.run_once(
        callback=test, 
        when=50, 
        data=(partita,update),
        name=f"{roba.chat.id} - {partita.prossimoTurno().idUtente}"
    )
    
    partita.nonsocomechiamarequestavariabile[idUtente] = await prova_messaggio(
        _("Tocca a {user}. Ultime 3 parole: {words}").format(
            user=partita.prossimoTurno().nomeUtente,
            words=partita.ottieniStoria(3)
        ),
        update=update,
        bot=context.bot
    )
    
    

async def test(context: ContextTypes.DEFAULT_TYPE):
    partita: Partita = context.job.data[0]
    update: Update = context.job.data[1]
    test = partita.getAllPartecipants().index(partita.prossimoTurno())
    await prova_messaggio(
        _("{user} ha impiegato troppo tempo per inviare una parola, skippo il turno a {next}").format(
            user = partita.prossimoTurno().nomeUtente,
            next = partita.getAllPartecipants()[(test + 1) % len(partita.getAllPartecipants())].nomeUtente
        ),
        update=update,
        bot = context.bot
    )
    partita.prossimoTurno().hasWritten = True
    
    if partita.everyone_has_written():
        for partecipante in partita.getAllPartecipants():
            partecipante.hasWritten = False
        
        messaggioDaCancellare = await prova_messaggio(
            _('Tutti i partecipanti hanno scritto una parola. Ora ricominciamo da {user}').format(user=partita.prossimoTurno().nomeUtente),
            update=update,
            bot=context.bot
        )
        
        sleep(3)
        await messaggioDaCancellare.delete()
        context.job_queue.run_once(callback=test, when=50, data=(partita,update),name=f"{partita.prossimoTurno().idUtente}")
        return

    
    

async def end_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global partite

    # Solito copia incolla
    roba = update.effective_message
    
    utente = roba.from_user.name
    idUtente = str(roba.from_user.id)
    chat_id = roba.chat.id
    messaggio = roba.text
    messaggio_id = roba.message_id

    cambiaLingua(idUtente,users.getUserLang(idUtente))

    if idUtente in MASTER_ADMIN:
        if len(messaggio.split(" ")) > 2:
            await prova_messaggio(_("Devi scrivere solo l'ID del gruppo in cui terminare la partita dopo il comando, non altro"),update=update,bot=context.bot)
        else:
            if len(messaggio.split(" ")) > 1:
                selected_id = str(messaggio.split(" ")[1])
                if selected_id == "this":
                    selected_id = chat_id
            else:
                selected_id = chat_id
            selected_id = str(selected_id)
            if selected_id not in partite:
                await prova_messaggio(_("Il gruppo selezionato non è in partita."),update=update,bot=context.bot)
                return
            partita = partite[selected_id]
            
            # Se la storia non è vuota la stampi, altrimenti termini la partita e basta
            if (len(partita.storia) > 0):
                await context.bot.send_message(chat_id=selected_id,text=_("Partita terminata forzatamente da un admin del bot. Ecco la vostra storia:"))
                await context.bot.send_message(chat_id=selected_id,text=_("#storia\n\n{story}").format(story=capwords(partita.ottieniStoria(), '. ').replace(' .', '.').replace(' ,', ',')))
            else:
                await context.bot.send_message(chat_id=selected_id,text=_("Partita terminata forzatamente da un admin del bot."))
            
            if selected_id != str(roba.chat_id):
                prova_messaggio(
                    _("Partita terminata con successo in {group_name}").format(
                        group_name = (await context.bot.get_chat(selected_id)).effective_name
                    ),
                    update=update,
                    bot=context.bot
                )
            # Azzero qualsiasi cosa possibile per cancellare la partita
            partite.pop(f'{selected_id}', None)
            for partecipante in partita.getAllPartecipants():
                current_jobs = context.job_queue.get_jobs_by_name(f"{roba.chat.id} - {partecipante.idUtente}")
                if current_jobs:
                    for job in current_jobs:
                        job.schedule_removal()
        return # Non continuo
    
    # Se la partita non esiste non puoi terminarla
    if not f'{chat_id}' in partite:
        await prova_messaggio(_("Devi prima creare una partita."),update=update,bot=context.bot)
        return

    partita = partite[f"{chat_id}"]
    
    # Se non sei il leader della partita o un admin non puoi terminarla
    utenti_che_possono_cancellare: list[ChatMemberAdministrator | ChatMemberOwner] = []
    
    for utente in await update.message.chat.get_administrators():
        utente: ChatMemberAdministrator | ChatMemberOwner
        if utente is ChatMemberAdministrator and utente.can_delete_messages:
            utenti_che_possono_cancellare.append(utente)
        elif utente is ChatMemberOwner:
            utenti_che_possono_cancellare.append(utente)
            
    if idUtente != partita.leaderId or not idUtente in [str(k.user.id) for k in utenti_che_possono_cancellare]:
        await prova_messaggio(_(
            "{utente} non hai avviato tu la partita! Puoi usare /quit_ows_game al massimo").format(utente=utente.user.name),
            update=update,
            bot=context.bot
        )
        return

    # Se la storia non è vuota la stampi, altrimenti termini la partita e basta
    if (len(partita.storia) > 0):
        await prova_messaggio(_("Termino la partita. Ecco la vostra storia:"),update=update,bot=context.bot)
        await prova_messaggio(_("#storia\n\n{story}").format(story=capwords(partita.ottieniStoria(), '. ').replace(' .', '.').replace(' ,', ',')),update=update,bot=context.bot)
    else:
        await prova_messaggio(_("Termino la partita."),update=update,bot=context.bot)

    # Azzero qualsiasi cosa possibile per cancellare la partita
    
    for partecipante in partita.getAllPartecipants():
        current_jobs = context.job_queue.get_jobs_by_name(f"{roba.chat.id} - {partecipante.idUtente}")
        if current_jobs:
            for job in current_jobs:
                job.schedule_removal()

    partite.pop(f'{chat_id}', None)
    

async def quit_ows_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global partite

    # Solito copia incolla
    
    roba = update.effective_message
    
    utente = roba.from_user.name
    idUtente = str(roba.from_user.id)
    chat_id = roba.chat.id
    messaggio = roba.text
    messaggio_id = roba.message_id

    cambiaLingua(str(idUtente),users.getUserLang(str(idUtente)))

    # Se non esiste una partita non puoi quittarla e.e
    if not f'{chat_id}' in partite:
        await prova_messaggio(_('Non è stata creata nessuna partita. Creane una con /crea_partita'),
            update=update,
            bot=context.bot
        )
        return

    partita = partite[f"{chat_id}"]

    # Se l'utente non partecipa alla partita non può quittare lol
    if not idUtente in partita.partecipanti:
        await prova_messaggio(
            _('Non sei in partita!'),
            update=update,
            bot=context.bot
        )
        return

    # Se passi tutti i controlli togli l'utente dai partecipanti e ristampa la lista
    partita.partecipanti.pop(idUtente)
    mess = await prova_messaggio(
        _("Sei uscito dalla partita con successo.\n\nPartecipanti restanti:\n{remain}").format(remain=partita.getAllPartecipantsString()),
        update=update,
        bot=context.bot
    )
    
    # Nuova lista da aggiornare se qualcuno joina
    partite[f'{chat_id}'].MessaggioListaPartecipanti = mess

async def skip_turn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global partite

    roba = update.effective_message
        
    utente = roba.from_user.name
    idUtente = str(roba.from_user.id)
    chat_id = roba.chat.id
    messaggio = roba.text
    messaggio_id = roba.message_id

    cambiaLingua(idUtente,users.getUserLang(idUtente))

    # Se la partita non esiste
    if not f'{chat_id}' in partite:
        await prova_messaggio(
            _("Devi prima creare una partita."),
            update=update,
            bot=context.bot
        )
        return

    partita = partite[f"{chat_id}"]

    if not partita.isStarted:
        await prova_messaggio(
            _("La partita non è stata ancora avviata."),
            update=update, 
            bot=context.bot
        )

    # Se l'utente non partecipa alla partita non può skippare
    if not idUtente in partita.partecipanti:
        await prova_messaggio(
            _('Non puoi votare, non sei in partita!'),
            update=update,
            bot=context.bot
        )
        return

    if idUtente == partita.prossimoTurno().idUtente:
        await prova_messaggio(
            _('Non puoi votare per skippare il tuo stesso turno!'),
            update=update,
            bot=context.bot
        )
        return
        

    if partita.getVotes() == 0:  
        partita.skipping = True
        mess = await prova_messaggio(
            _('{utente} ha avviato la votazione per skippare il turno di {turn}.\n{voteStatus}/{totalPlayers}').format(
                utente = utente,
                turn = partita.prossimoTurno().nomeUtente, 
                voteStatus = partita.getVotes(),
                totalPlayers = partita.getNumberOfPlayers()
            ),
            update=update,
            bot=context.bot
        )
        partita.MessaggioVoteSkip = mess
    
    partita.partecipanti[idUtente].voteSkip = True
    try:
        await context.bot.edit_message_text(chat_id = chat_id, message_id = partita.MessaggioVoteSkip.message_id, text = f"{partita.MessaggioVoteSkip.text[0:partita.MessaggioVoteSkip.text.rfind('.')+1]}\n{partita.getVotes()}/{partita.getNumberOfPlayers() - 1}")
    except:
        prova_messaggio(
            text = (f"{partita.MessaggioVoteSkip.text[0:partita.MessaggioVoteSkip.text.rfind('.')+1]}\n" +
                f"{partita.getVotes()}/{partita.getNumberOfPlayers() - 1}"),
            update=update,
            bot=context.bot
        )

    if partita.getVotes() >= partita.getNumberOfPlayers() - 1:
        voti_attuali = partite[f"{chat_id}"].getVotes()
        player_totali = partite[f"{chat_id}"].getNumberOfPlayers()
        await prova_messaggio(
            _('{votes} voti di {totalPlayers}, skip confermato.').format(
                votes=voti_attuali,totalPlayers=player_totali
            ),
            update=update,
            bot=context.bot
        )
        partita.partecipanti[f"{partita.prossimoTurno().idUtente}"].hasWritten = True
        
        current_jobs = context.job_queue.get_jobs_by_name(f"{roba.chat.id} - {idUtente}")
        if current_jobs:
            for job in current_jobs:
                job.schedule_removal()

        for partecipante in partite[f"{chat_id}"].getAllPartecipants():
            partecipante.voteSkip = False
        
        if partita.everyone_has_written():
            for id in partita.getAllPartecipantsIDs():
                partita.partecipanti[f'{id}'].hasWritten = False

            messaggioDaCancellare = await prova_messaggio(
                _('Tutti i partecipanti hanno scritto una parola. Ora ricominciamo da {turno}.\n\nUltime 3 parole: {words}').format(
                    turno=partite[f"{chat_id}"].getAllPartecipants()[0].nomeUtente,
                    words=partita.ottieniStoria(3)
                ),
                update=update,
                bot=context.bot
            )
            sleep(3)
            await context.bot.delete_message(chat_id, messaggioDaCancellare.message_id)


async def wakeUp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global partite

    # Solito copia incolla
    utente = ('@' + update.message.from_user.username) if update.message.from_user.username != None else update.message.from_user.full_name
    idUtente = update.message.from_user.id
    chat_id = update.message.chat.id
    messaggio = update.message.text
    messaggio_id = update.message.message_id

    cambiaLingua(str(idUtente),users.getUserLang(str(idUtente)))

    # Se la partita non esiste
    if not f'{chat_id}' in partite:
        await prova_messaggio(_("Devi prima partecipare ad una partita."),update=update,
                    bot=context.bot)
        return

    # Se la partita è avviata
    if not partite[f'{chat_id}'].isStarted:
        await prova_messaggio(_("Partita non avviata"),update=update,
                    bot=context.bot)
        return
    
    await prova_messaggio(_("Sveglia {turno}, tocca a te!").format(turno=partite[f'{chat_id}'].prossimoTurno().nomeUtente),update=update,bot=context.bot)
    

# Segnala quando il bot crasha, con motivo del crash
async def error(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.warning('Update "%s" caused error "%s"', update, context.error)
    await context.bot.send_message(ID_CANALE_LOG, text=f'{context.bot.name}\nUpdate "{update}" caused error "{context.error}')


async def lingua(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await prova_messaggio("To be translated...",update=update, bot=context.bot)
    return
    
    keyboard = [
        [
            InlineKeyboardButton("Italiano", callback_data="Italiano,it"),
            InlineKeyboardButton("English", callback_data="English,en"),
        ]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await prova_messaggio("Select a language",reply_markup=reply_markup,update=update,
                    bot=context.bot)

async def linguaPremuta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(text=f"Selected option: {query.data.split(',')[0]}")
    
    id = str(query.from_user.id)
    
    if not users.userExists(id):
        users.saveUser(id, ('@' + query.from_user.username) if query.from_user.username != None else query.from_user.full_name, await query.data.split(',')[1])
    else:
        users.editUserLang(id, await query.data.split(',')[1])
    
    cambiaLingua(id,query.data.split(',')[1])

    
def cambiaLingua(id: str, lingua: str):
    return 
    lingua = lingua.replace('\n','')

    lingue_possibli = ["it","en"]
    
    if not lingua in lingue_possibli:
        lingua = "en"

    lang = gettext.translation('base',localedir='locales', languages=[lingua])
    lang.install()
    
    
    global _
    _ = lang.gettext


def main():
    # Avvia il bot

    # Crea l'Updater e passagli il token del tuo bot
    # Accertati di impostare use_context=True per usare i nuovi context-based callbacks (non so cosa siano)
    # Dalla versione 12 non sarà più necessario
    application = Application.builder().token(TOKEN).build() # Se si vuole usare la PicklePersistance bisogna aggiungere dopo .token(TOKEN) anche .persistance(OGGETTO_PP)

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("crea_partita", crea_partita))
    application.add_handler(CommandHandler("join_ows_game", join_ows_game))
    application.add_handler(CommandHandler("avvia_partita", avvia_partita))
    application.add_handler(CommandHandler("end_game", end_game))
    application.add_handler(CommandHandler("quit_ows_game", quit_ows_game))
    application.add_handler(CommandHandler("skip_turn",skip_turn))
    application.add_handler(CommandHandler("wakeUp",wakeUp))
    
    application.add_handler(CommandHandler("changeLanguage",lingua))
    application.add_handler(CallbackQueryHandler(linguaPremuta))

    # Legge i messaggi dei gruppi e supergruppi ma non i comandi, per permettere /end_game e /quit_ows_game
    application.add_handler( 
        MessageHandler(
            filters.ChatType.GROUPS & 
            filters.TEXT &
            ~filters.COMMAND, onMessageInGroup, block=False)
        ) 

    # In caso di errore vai nel metodo "error"
    application.add_error_handler(error)

    # Avvia il bot con il polling
    application.run_polling()


# Se avvii il programma direttamente va qui, altrimenti se lo usi tipo come libreria no
if __name__ == '__main__':
    main()
