import logging # Per loggare (non si usa "print()" ma logger.info())

from string import capwords
from typing import Dict
from time import sleep
import requests


from telegram import (
    Bot,
    ParseMode,
    Update, # È il tipo che usiamo nelle funzioni
    Message, # Il tipo per i messaggi
    InlineKeyboardButton,
    InlineKeyboardMarkup
)

import gettext
import users

from telegram.ext import (
    Updater, # Per il bot
    CommandHandler, # Per i comandi
    CallbackContext, # Tipo del parametro "context" di tutti i metodi
    MessageHandler, # Per i messaggi
    Filters, # Per i messaggi (i filtri tipo per dire: Agisci quando ricevi immagini, file, audio, tutto e cose così)
    CallbackQueryHandler,
)


TOKEN = None  # TOKEN DEL BOT
with open('token.txt', 'r') as f:
    TOKEN = f.read().strip()

# ID TELEGRAM PER RICEVERE NOTIFICA (ottienilo con t.me/JsonDumpBot)
MASTER_ADMIN = [245996916]
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
        self.idUtente = id
        self.hasWritten = False
        self.voteSkip = False
        self.asleep = False
        self.MessaggiDaCancellare: list[Message] = []


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
        self.leaderId: int = userId
        self.partecipanti: Dict[str, Partecipante] = {}
        self.isStarted: bool = False
        self.MessaggioListaPartecipanti: Message = mess
        self.MessaggioVoteSkip: Message

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

    def getVotes(self):
        voti: int = 0
        for partecipante in self.getAllPartecipants():
            if partecipante.voteSkip:
                voti += 1
        
        return voti


#        group_id: Partita
partite: Dict[str, Partita] = {}

#       group_id: storia
storie: Dict[str, str] = {}

def start(update: Update, context: CallbackContext):  # /start
    
    utente = ('@' + update.message.from_user.username) if update.message.from_user.username != None else update.message.from_user.full_name
    idUtente = update.message.from_user.id

    users.saveUser(str(idUtente), utente, update.message.from_user.language_code)
    cambiaLingua(str(idUtente),users.getUserLang(str(idUtente)))

    logging.info(f'{utente}, {idUtente} - Ha eseguito /start')
    prova_messaggio(_(
        'Benvenuto nel bot "One Word Story". Per giocare aggiungimi in un gruppo e fai /crea_partita'),
                    update=update,
                    bot=context.bot)


def prova_messaggio(messaggio:str, update: Update, bot: Bot, parse_mode=ParseMode.HTML, reply_markup=None):
    try: 
        return update.message.reply_text(
            messaggio, 
            parse_mode=parse_mode,
            reply_markup=reply_markup
        )
    except:
        return bot.send_message(
            chat_id = update.message.chat_id,
            text = messaggio,
            parse_mode = parse_mode,
            reply_markup=reply_markup
        )

def crea_partita(update: Update, context: CallbackContext):
    global partite

    # Assegno tutte le variabili per comodità
    utente = ('@' + update.message.from_user.username) if update.message.from_user.username != None else update.message.from_user.full_name
    idUtente = update.message.from_user.id

    chat_id = update.message.chat.id

    cambiaLingua(str(idUtente),users.getUserLang(str(idUtente)))

    # Controllo se la chat è una chat privata, se sì esce dalla funzione
    if chat_id > 0:
        prova_messaggio(_(
            'Hey {utente}, non vorrai mica giocare da solo? Usa questo comando in un gruppo').format(utente=utente),update=update,
                    bot=context.bot)
        return

    # Se la chat non è presente nella lista delle partite
    if not f'{chat_id}' in partite:
        
        mess = prova_messaggio(_(
            '{utente} ha creato una partita. Entra con /join_ows_game.\n\nPartecipanti:\n- {utente}').format(utente=utente),update=update,
                    bot=context.bot)

        if not context.bot.getChatMember(chat_id,context.bot.id).can_delete_messages:
            prova_messaggio(_('Il bot non ha i permessi per cancellare i messaggi, si può giocare comunque, ma consiglio di darglieli.'),update=update,
                    bot=context.bot)

        partite[f'{chat_id}'] = Partita(utente, idUtente, mess=mess) # Crea la partita con l'utente leader (chi l'ha creata)
        storie[f'{chat_id}'] = '' # Inizializzo la variabile storie per la chat a cui andrò a concatenare le varie parole
        partite[f'{chat_id}'].partecipanti[f'{idUtente}'] = Partecipante(
            utente, idUtente) # Aggiungo il creatore ai partecipanti
        logging.info(f'{utente}, {idUtente} - Ha creato una partita nel gruppo {update.message.chat.title}')
    else: # Avviso se la partita è già presente nella lista
        prova_messaggio(_(
            'Partita già creata. Entra con /join_ows_game'),update=update,
                    bot=context.bot)



def join_ows_game(update: Update, context: CallbackContext):
    global partite

    # Assegno tutte le variabili per comodità
    # "utente" fa il controllo se l'username è presente altrimenti usa il nome
    utente = ('@' + update.message.from_user.username) if update.message.from_user.username != None else update.message.from_user.full_name
    idUtente = update.message.from_user.id
    chat_id = update.message.chat.id

    cambiaLingua(str(idUtente),users.getUserLang(str(idUtente)))

    # Controllo se per la chat esiste una partita
    if not f'{chat_id}' in partite:
        prova_messaggio(_(
            'Non è stata creata nessuna partita. Creane una con /crea_partita'),update=update,
                    bot=context.bot)
        return

    # Controllo se l'utente è già nella lista dei partecipanti della partita
    if str(idUtente) in partite[f'{chat_id}'].partecipanti:
        prova_messaggio(_('Partecipi già alla partita!'),update=update,
                    bot=context.bot)
        return


    # Creo il nuovo partecipante
    partite[f'{chat_id}'].partecipanti[f'{idUtente}'] = Partecipante(
        utente, idUtente)
    
    # Modifica il messaggio di creazione della partita per mostrare la lista dei partecipanti al game
    partite[f'{chat_id}'].MessaggioListaPartecipanti = context.bot.edit_message_text(
        chat_id=chat_id, message_id=partite[f'{chat_id}'].MessaggioListaPartecipanti.message_id, text=partite[f'{chat_id}'].MessaggioListaPartecipanti.text + f"\n- {utente}")

    prova_messaggio(_('{utente} è entrato nella partita').format(utente=utente),update=update,
                    bot=context.bot)

def avvia_partita(update: Update, context: CallbackContext):
    global partite

    # Solite variabili per comodità
    utente = ('@' + update.message.from_user.username) if update.message.from_user.username != None else update.message.from_user.full_name
    idUtente = update.message.from_user.id
    chat_id = update.message.chat.id
    
    cambiaLingua(str(idUtente),users.getUserLang(str(idUtente)))
    
    # Se la partita non esiste
    if not f'{chat_id}' in partite: 
        prova_messaggio(_(
            'Non è stata creata nessuna partita. Creane una con /crea_partita'),update=update,
                    bot=context.bot)
        return

    # Se un utente che non è il creatore prova ad avviare la partita, non può
    if not idUtente == partite[f'{chat_id}'].leaderId:
        prova_messaggio(_("Non hai creato tu la partita"),update=update,
                    bot=context.bot)
        return

    # Controlla se la partita è già avviata
    if partite[f'{chat_id}'].isStarted:
        prova_messaggio(_("Partita già avviata"),update=update,
                    bot=context.bot)
        return

    # Se tutti i controlli sono andati a buon fine, avvia la partita
    partite[f'{chat_id}'].isStarted = True 

    if context.bot.getChatMember(chat_id,context.bot.id).can_delete_messages:
        prova_messaggio(_(
            "{utente} ha avviato la partita. Prenderò una parola a testa da ognuno di voi in ordine, per poi comporre una storia da esse, inoltre da ora cancellerò tutti i messaggi dei partecipanti che:\n - Non contengono una parola sola;\n - Hanno già scritto una parola.\n\nMetti * o / all\'inizio di un messaggio per non farlo cancellare dal bot\n\nL'ordine dei turni è:\n").format(utente=utente) + partite[f'{chat_id}'].getAllPartecipantsString(),update=update,
                    bot=context.bot)
    else:
        prova_messaggio(_(
            "{utente} ha avviato la partita. Prenderò una parola a testa da ognuno di voi in ordine, per poi comporre una storia da esse.\n\nL'ordine dei turni è:\n").format(utente=utente) + partite[f'{chat_id}'].getAllPartecipantsString(),update=update,
                    bot=context.bot)

# Questo metodo è avviato asincrono per poter usare sleep per cancellare i messaggi dopo tot secondi
def onMessageInGroup(update: Update, context: CallbackContext):
    global partite

    # Variabili per comodità
    # Ora tutte queste variabili hanno un controllo in più,
    # questo per evitare errori in caso il messaggio ricevuto sia
    # un messaggio modificato e non un messaggio nuovo.
    # (Se il messaggio è modificato l'update sarà edited_message e non message)
    chat_id = update.message.chat.id if update.message != None else update.edited_message.chat.id
    utente = (('@' + update.message.from_user.username) if update.message.from_user.username != None else update.message.from_user.full_name) if update.message != None else (
        update.edited_message.from_user.username if update.edited_message.from_user.username != None else update.edited_message.from_user.full_name)
    idUtente = update.message.from_user.id if update.message != None else update.edited_message.from_user.id
    messaggio_id = update.message.message_id if update.message != None else update.edited_message

    cambiaLingua(str(idUtente),users.getUserLang(str(idUtente)))

    # Se la partita non esiste o non è stata avviata non fare nulla
    if (not f'{chat_id}' in partite) or (not partite[f'{chat_id}'].isStarted):
        return

    # Se l'utente non è in partita, non fare nulla
    if not str(idUtente) in partite[f'{chat_id}'].getAllPartecipantsIDs():
        return
    
    
    # Se il messaggio è modificato, non aggiornare la storia
    if update.edited_message != None:
        prova_messaggio(_(
            'Hey {utente}, non puoi modificare un messaggio! La tua parola rimarrà la stessa').format(utente=utente),
                        update=update, bot=context.bot)
        return

    messaggio = update.message.text 

    # Caratteri per far scrivere agli utenti senza far considerare i messaggi dal bot
    if messaggio[0:1] == '/' or messaggio[0:1] == '*':
        return
    
    # Se non è il turno dell'utente avvisa e cancella il messaggio
    if not idUtente == partite[f'{chat_id}'].prossimoTurno().idUtente:
        messaggioDaCancellare = prova_messaggio(_(
            "{utente}, non è il tuo turno. Tocca a {turno}").format(utente=utente, turno=partite[f'{chat_id}'].prossimoTurno().nomeUtente),update=update,
                    bot=context.bot)
        
        # Controllo che il bot possa cancellare i messaggi
        if context.bot.getChatMember(chat_id,context.bot.id).can_delete_messages:
            context.bot.delete_message(chat_id, messaggio_id)
            sleep(3)
            context.bot.delete_message(chat_id, messaggioDaCancellare.message_id)
        return
    
    

    # Se il messaggio contiene uno dei seguenti caratteri avvisa e cancella il messaggio
    if (' ' in messaggio or '_' in messaggio or '-' in messaggio or '+' in messaggio):
        messaggioDaCancellare = prova_messaggio(_(
            '{utente}, devi scrivere una parola sola :P\nil gioco si chiama "ONE WORD stories" per un motivo.').format(utente=utente),update=update,
                    bot=context.bot)
        
        # Controllo che il bot possa cancellare i messaggi
        if context.bot.getChatMember(chat_id,context.bot.id).can_delete_messages:
            context.bot.delete_message(chat_id, messaggio_id)
            sleep(3)
            context.bot.delete_message(chat_id, messaggioDaCancellare.message_id)
        return

    max_caratteri = 15

    # Se il messaggio è troppo lungo avvia e cancella il messaggio
    if (len(messaggio) > max_caratteri):
        messaggioDaCancellare = prova_messaggio(_(
            '{utente}, il messaggio è troppo lungo (più di {max_caratteri})').format(utente=utente, max_caratteri=max_caratteri),update=update,
                    bot=context.bot)
        
        # Controllo che il bot possa cancellare i messaggi
        if context.bot.getChatMember(chat_id,context.bot.id).can_delete_messages:
            context.bot.delete_message(chat_id, messaggio_id)
            sleep(3)
            context.bot.delete_message(chat_id, messaggioDaCancellare.message_id)
        return

    partecipante = partite[f'{chat_id}'].partecipanti[str(idUtente)]

    # Se il partecipante ha già scritto avvisa e cancella il messaggio
    if partecipante.hasWritten:
        messaggioDaCancellare = prova_messaggio(_(
            '{utente} hai già scritto una parola.').format(utente=utente),update=update,
                    bot=context.bot)
        
        # Controllo che il bot possa cancellare i messaggi
        if context.bot.getChatMember(chat_id,context.bot.id).can_delete_messages:
            context.bot.delete_message(chat_id, messaggio_id)
            sleep(3)
            context.bot.delete_message(chat_id, messaggioDaCancellare.message_id)
        return

    if partecipante.asleep:
        if context.bot.getChatMember(chat_id,context.bot.id).can_delete_messages:
            for mex in partecipante.MessaggiDaCancellare:
                context.bot.delete_message(chat_id, mex.message_id)
            partecipante.MessaggiDaCancellare = []
        partecipante.asleep = False

    storie[str(chat_id)] += messaggio + ' ' # Aggiungi il messaggio alla storia 
                                            # (avrei potuto mettere la stringa dentro il dictionary partite
                                            #  ma ora non ho voglia di cambiare tutto)

    partecipante.hasWritten = True # True, ha scritto



    # Se hanno scritto tutti, metti a tutti "hasWritten = false"
    if all_partecipants_have_written(partite[f'{chat_id}']):
        for id in partite[f'{chat_id}'].getAllPartecipantsIDs():
            partite[f'{chat_id}'].partecipanti[f'{id}'].hasWritten = False

        messaggioDaCancellare = prova_messaggio(_(
            'Tutti i partecipanti hanno scritto una parola. Ora ricominciamo da {turno}').format(turno=partite[f"{chat_id}"].getAllPartecipants()[0].nomeUtente),update=update,
                    bot=context.bot)
        sleep(3)
        context.bot.delete_message(chat_id, messaggioDaCancellare.message_id)


# Questo metodo potevo farlo dentro la classe "Partita" però ora non ho voglia di cambiare tutto
def all_partecipants_have_written(partita: Partita) -> bool:

    for idPartecipante in partita.getAllPartecipantsIDs():
        if not partita.partecipanti[f'{idPartecipante}'].hasWritten:
            return False

    return True

def end_game(update: Update, context: CallbackContext):
    global partite

    # Solito copia incolla
    utente = ('@' + update.message.from_user.username) if update.message.from_user.username != None else update.message.from_user.full_name
    idUtente = update.message.from_user.id
    chat_id = update.message.chat.id
    messaggio = update.message.text
    messaggio_id = update.message.message_id

    cambiaLingua(str(idUtente),users.getUserLang(str(idUtente)))

    if idUtente in MASTER_ADMIN:
        if len(messaggio.split(" ")) > 2:
            prova_messaggio(_("Devi scrivere solo l'ID del gruppo in cui terminare la partita dopo il comando, non altro"),update=update,bot=context.bot)
        else:
            if len(messaggio.split(" ")) > 1:
                selected_id = str(messaggio.split(" ")[1])
                if selected_id == "this":
                    selected_id = chat_id
            else:
                selected_id = chat_id
            
            if str(selected_id) not in partite:
                prova_messaggio(_("Il gruppo selezionato non è in partita."),update=update,bot=context.bot)
                return
            
            # Se la storia non è vuota la stampi, altrimenti termini la partita e basta
            if (storie[f'{selected_id}'] != ""):
                context.bot.send_message(chat_id=selected_id,text=_("Partita terminata forzatamente da un admin del bot. Ecco la vostra storia:"))
                context.bot.send_message(chat_id=selected_id,text=_("#storia\n\n{story}").format(story=capwords(storie[f'{selected_id}'], '. ').replace(' .', '.').replace(' ,', ',')))
            else:
                context.bot.send_message(chat_id=selected_id,text=_("Partita terminata forzatamente da un admin del bot."))
            # Azzero qualsiasi cosa possibile per cancellare la partita
            partite.pop(f'{selected_id}', None)
            storie.pop(f'{selected_id}', None)
        return # Non continuo
    
    
    # Se la partita non esiste non puoi terminarla
    if not f'{chat_id}' in partite:
        prova_messaggio(_("Devi prima creare una partita."),update=update,bot=context.bot)
        return

    # Se non sei il leader della partita non puoi terminarla
    if idUtente == partite[f'{chat_id}'].leaderId or idUtente in [user.user.id for user in update.message.chat.get_administrators() if user.can_manage_chat]:
        prova_messaggio(_(
            "{utente} non hai avviato tu la partita! Puoi usare /quit_ows_game al massimo").format(utente=utente),update=update,
                    bot=context.bot)
        return

    # Se la storia non è vuota la stampi, altrimenti termini la partita e basta
    if (storie[f'{chat_id}'] != ""):
        prova_messaggio(_("Termino la partita. Ecco la vostra storia:"),update=update,
                    bot=context.bot)
        prova_messaggio(_("#storia\n\n{story}").format(story=capwords(storie[f'{chat_id}'], '. ').replace(' .', '.').replace(' ,', ',')),update=update,
                    bot=context.bot)
    else:
        prova_messaggio(_("Termino la partita."),update=update,
                    bot=context.bot)

    # Azzero qualsiasi cosa possibile per cancellare la partita
    partite.pop(f'{chat_id}', None)
    storie.pop(f'{chat_id}', None)

def quit_ows_game(update: Update, context: CallbackContext):
    global partite

    # Solito copia incolla
    utente = ('@' + update.message.from_user.username) if update.message.from_user.username != None else update.message.from_user.full_name
    idUtente = update.message.from_user.id
    chat_id = update.message.chat.id
    messaggio = update.message.text
    messaggio_id = update.message.message_id

    cambiaLingua(str(idUtente),users.getUserLang(str(idUtente)))

    # Se non esiste una partita non puoi quittarla e.e
    if not f'{chat_id}' in partite:
        prova_messaggio(_(
            'Non è stata creata nessuna partita. Creane una con /crea_partita'),update=update,
                    bot=context.bot)
        return

    # Se l'utente non partecipa alla partita non può quittare lol
    if not str(idUtente) in partite[f'{chat_id}'].partecipanti:
        prova_messaggio(_('Non sei in partita!'),update=update,
                    bot=context.bot)
        return

    # Se passi tutti i controlli togli l'utente dai partecipanti e ristampa la lista
    partite[f'{chat_id}'].partecipanti.pop(str(idUtente))
    mess = prova_messaggio(_("Sei uscito dalla partita con successo.\n\nPartecipanti restanti:\n{remain}").format(remain=partite[f'{chat_id}'].getAllPartecipantsString()),update=update,
                    bot=context.bot)
    
    # Nuova lista da aggiornare se qualcuno joina
    partite[f'{chat_id}'].MessaggioListaPartecipanti = mess

def skip_turn(update: Update, context: CallbackContext):
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
        prova_messaggio(_("Devi prima partecipare ad una partita."),update=update,
                    bot=context.bot)
        return

    if not partite[f'{chat_id}'].isStarted:
        prova_messaggio(_("La partita non è stata ancora avviata."),update=update, bot=context.bot)

    # Se l'utente non partecipa alla partita non può skippare
    if not str(idUtente) in partite[f'{chat_id}'].partecipanti:
        prova_messaggio(_('Non puoi votare, non sei in partita!'),update=update,
                    bot=context.bot)
        return

    if partite[f'{chat_id}'].getVotes() == 0: # 
        mess = prova_messaggio(_('{utente} ha avviato la votazione per skippare il turno di {turno}.\n{voteStatus}/{totalPlayers}').format(utente=utente, turno=partite[f"{chat_id}"].prossimoTurno().nomeUtente, voteStatus=partite[f"{chat_id}"].getVotes(), totalPlayers=partite[f"{chat_id}"].getNumberOfPlayers()),update=update,
                    bot=context.bot)
        partite[f'{chat_id}'].MessaggioVoteSkip = mess
    
    
    partite[f'{chat_id}'].partecipanti[f'{idUtente}'].voteSkip = True
    context.bot.edit_message_text(chat_id = chat_id, message_id = partite[f'{chat_id}'].MessaggioVoteSkip.message_id, text = f"{partite[f'{chat_id}'].MessaggioVoteSkip.text[0:partite[f'{chat_id}'].MessaggioVoteSkip.text.rfind('.')+1]}\n{partite[f'{chat_id}'].getVotes()}/{partite[f'{chat_id}'].getNumberOfPlayers() - 1}")

    if partite[f'{chat_id}'].getVotes() >= partite[f'{chat_id}'].getNumberOfPlayers() - 1:
        voti_attuali = partite[f"{chat_id}"].getVotes()
        player_totali = partite[f"{chat_id}"].getNumberOfPlayers()
        prova_messaggio(_('{votes} voti di {totalPlayers}, skip confermato.').format(votes=voti_attuali,totalPlayers=player_totali),update=update,
                    bot=context.bot)
        partite[f'{chat_id}'].partecipanti[f"{partite[f'{chat_id}'].prossimoTurno().idUtente}"].hasWritten = True

        for partecipante in partite[f"{chat_id}"].getAllPartecipants():
            partecipante.voteSkip = False
        
        if all_partecipants_have_written(partite[f'{chat_id}']):
            for id in partite[f'{chat_id}'].getAllPartecipantsIDs():
                partite[f'{chat_id}'].partecipanti[f'{id}'].hasWritten = False

            messaggioDaCancellare = prova_messaggio(_(
                'Tutti i partecipanti hanno scritto una parola. Ora ricominciamo da {turno}').format(turno=partite[f"{chat_id}"].getAllPartecipants()[0].nomeUtente),update=update,
                    bot=context.bot)
            sleep(3)
            context.bot.delete_message(chat_id, messaggioDaCancellare.message_id)


def wakeUp(update: Update, context: CallbackContext):
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
        prova_messaggio(_("Devi prima partecipare ad una partita."),update=update,
                    bot=context.bot)
        return

    # Se la partita è avviata
    if not partite[f'{chat_id}'].isStarted:
        prova_messaggio(_("Partita non avviata"),update=update,
                    bot=context.bot)
        return
    
    #prova_messaggio(_(f"Sveglia {partite[f'{chat_id}'].prossimoTurno().nomeUtente}, tocca a te!")
    partite[f"{chat_id}"].prossimoTurno().MessaggiDaCancellare.append(update.message)
    partite[f"{chat_id}"].prossimoTurno().MessaggiDaCancellare.append(prova_messaggio(_("Sveglia {turno}, tocca a te!").format(turno=partite[f'{chat_id}'].prossimoTurno().nomeUtente),update=update,
                    bot=context.bot))
    partite[f"{chat_id}"].prossimoTurno().asleep = True
    

# Segnala quando il bot crasha, con motivo del crash
def error(update: Update, context: CallbackContext):
    if (context.error is requests.exceptions.ConnectionError):
        logger.warn("Qualcosa è andato storto con la connessione, dormo 2 secondi")
        sleep(2)
    else:
        logger.warning('Update "%s" caused error "%s"', update, context.error)
        context.bot.send_message(ID_CANALE_LOG, text=f'{context.bot.name}\nUpdate "{update}" caused error "{context.error}')


def lingua(update: Update, context: CallbackContext):
    prova_messaggio("WiP...",update=update, bot=context.bot)
    return
    
    keyboard = [
        [
            InlineKeyboardButton("Italiano", callback_data="Italiano,it"),
            InlineKeyboardButton("English", callback_data="English,en"),
        ]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)
    
    prova_messaggio("Select a language",reply_markup=reply_markup,update=update,
                    bot=context.bot)

def linguaPremuta(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()

    query.edit_message_text(text=f"Selected option: {query.data.split(',')[0]}")
    
    id = str(query.from_user.id)
    
    if not users.userExists(id):
        users.saveUser(id, ('@' + query.from_user.username) if query.from_user.username != None else query.from_user.full_name, query.data.split(',')[1])
    else:
        users.editUserLang(id, query.data.split(',')[1])
    
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
    updater = Updater(TOKEN, use_context=True)

    # Prendi il dispatcher per registrarci gli handlers (tipo comandi e messaggi)
    dp = updater.dispatcher

    # add_handler "aggiungi qualcosa" che definisci dentro, in questo caso due "comandi" (quelli con lo slash)
    # sintassi: add_handler(CommandHandler("scritta_dopo_lo_slash",metodo))

    # CommandHandler per i comandi
    # MessageHandler per i messaggi
    # Ci sono vari handler che trovi al link alla riga 4

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("crea_partita", crea_partita))
    dp.add_handler(CommandHandler("join_ows_game", join_ows_game))
    dp.add_handler(CommandHandler("avvia_partita", avvia_partita))
    dp.add_handler(CommandHandler("end_game", end_game))
    dp.add_handler(CommandHandler("quit_ows_game", quit_ows_game))
    dp.add_handler(CommandHandler("skip_turn",skip_turn))
    dp.add_handler(CommandHandler("wakeUp",wakeUp))

    dp.add_handler(CommandHandler("changeLanguage",lingua))
    dp.add_handler(CallbackQueryHandler(linguaPremuta))

    

    # Legge i messaggi dei gruppi e supergruppi ma non i comandi, per permettere /end_game e /quit_ows_game
    dp.add_handler( 
        MessageHandler(
            Filters.chat_type.groups & 
            Filters.text &
            ~Filters.command, onMessageInGroup, run_async=True) # async perché c'è sleep per aspettare i messaggi
            ) 

    
    # Questo per ricevere una notifica quando il bot è online; utile all'inizio, dopo disattivalo sennò impazzisci per le notifiche

    # In caso di errore vai nel metodo "error"
    dp.add_error_handler(error)

    # Avvia il bot con il polling
    updater.start_polling()

    # Con idle avvii il bot finché non premi CTRL-C o il processo riceve "SIGINT", "SIGTERM" o "SIGABRT".
    # Questo dovrebbe essere usato la maggior parte del tempo, in quanto start_polling() non è bloccante e interromperà il bot.
    updater.idle()



# Se avvii il programma direttamente va qui, altrimenti se lo usi tipo come libreria no
if __name__ == '__main__':
    main()
