import logging # Per loggare (non si usa "print()" ma logger.info())

from string import capwords
import gettext
import string
import users
import jsonpickle, os


from telegram.ext import (
    Application, # Per il bot
    CommandHandler, # Per i comandi
    MessageHandler, # Per i messaggi
    ConversationHandler, # Per più handler concatenati (Può salvare il suo stato con PicklePersistance)
    ContextTypes, # Per avere il tipo di context (ContextTypes.DEFAULT)
    CallbackQueryHandler, # Per gestire il click di un bottone o simile
    filters, # Per filtrare gli Handler 
    PicklePersistence, # Per un ConversationHandler, vedi https://gist.github.com/aahnik/6c9dd519c61e718e4da5f0645aa11ada#file-tg_conv_bot-py-L9t
    ExtBot,
    JobQueue
)

import telegram
from telegram import (
    Chat,
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

#region JSON
def toJSON(file: str, obj):
    with open(file,"w",encoding="utf8") as f:
        f.write(jsonpickle.encode(obj))

def fromJSON(file: str, ifFileEmpty = "[]"):
    if not os.path.exists(file):
        open(file,"w",encoding="utf8").close()
    
    with open(file,"r",encoding="utf8") as f:
        text = f.read()
        thing = jsonpickle.decode(text if text != "" else ifFileEmpty)
    return thing
#endregion

#TODO: Sistema di votazione per annullare l'ultima parola scritta

TOKEN = None  # TOKEN DEL BOT
with open('token.txt', 'r') as f:
    TOKEN = f.read().strip()

# ID TELEGRAM PER RICEVERE NOTIFICA (ottienilo con t.me/JsonDumpBot)
MASTER_ADMIN = ['245996916']
ID_CANALE_LOG = '-1001741378490'

# https://docs.python-telegram-bot.org/en/stable/telegram.ext.handler.html

# Questa è la configurazione di base del log, io lo lascio così di solito
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)

_ = gettext.gettext

def groupsConfig():
    return fromJSON("groupsConfig.json")

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
        self.voteWord = False


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
    SKIP_TMPL = _('{user} ha avviato la votazione per skippare il turno di {turn}.')
    
    def __init__(self, utente, userId, groupId, mess) -> None:
        self.leader: str = utente
        self.leaderId: str = str(userId)
        self.partecipanti: dict[str, Partecipante] = {}
        self.isStarted: bool = False
        self.MessaggioListaPartecipanti: Message = mess
        self.MessaggioVoteSkip: Message = None
        self.storia: list[Message] = []
        self.skipping: bool = False
        self.wakeUpMessages: dict[str,Message] = {}
        self.groupId = groupId
        self.skipVotes = 0
        self.voteWords = 0

        self.loadConfig()
        
        
    def loadConfig(self):
        gc = groupsConfig()
        if not str(self.groupId) in gc:
            gc[self.groupId] = fromJSON("defaultConfig.json")
            toJSON("groupsConfig.json",gc)
        
        groupConfig = groupsConfig()[str(self.groupId)]
        
        self.timerConfig: int = groupConfig['skiptime']
        self.wordHistoryConfig: int = groupConfig['wordHistory']
        self.maxWordsConfig: int = groupConfig['maxWords']
        self.maxWordsEffective: int = self.maxWordsConfig
        
    def addWord(self, word: Message):
        self.storia.append(word)
        
        pass

    def getAllPartecipantsIDs(self) -> list[str]:
        return list(self.partecipanti.keys())

    def getAllPartecipants(self) -> list[Partecipante]:
        return list(self.partecipanti.values())
    
    def getNumberOfPlayers(self) -> int:
        return len(list(self.getAllPartecipantsIDs()))

    def getAllPartecipantsString(self) -> str:
        listaStringa = ''
        
        for partecipante in self.getAllPartecipants():
            if partecipante != self.aChiTocca():
                listaStringa += '- ' + partecipante.nomeUtente + '\n'
            else:
                listaStringa += '→ ' + partecipante.nomeUtente + '\n'
        
        return listaStringa

    def aChiTocca(self) -> Partecipante:
        for partecipante in self.getAllPartecipantsIDs():
            if not self.partecipanti[partecipante].hasWritten:
                return self.partecipanti[partecipante]
        if not self.getAllPartecipants()[0].hasWritten:
            return self.getAllPartecipants()[0]

    def getLastTurn(self) -> Partecipante:
        partecipants = self.getAllPartecipants()
        for i, p in enumerate(partecipants):
            if not p.hasWritten:
                return partecipants[i-1]
    
    def resetVotesSkip(self):
        for partecipante in self.getAllPartecipants():
            partecipante.voteSkip = False
    
    def resetVotesCancel(self):
        self.voteWords = 0
        for partecipante in self.getAllPartecipants():
            partecipante.voteWord = False
    
    def ottieniStoria(self, parole=-1, link=False):
        if parole < -1:
            raise Exception("No valori negativi")
        elif parole == 0:
            return ""
        # elif parole == -1:
        #     return " ".join([formattaMessaggio(k.text) for k in self.storia])
        qwndfiu = ''
        for i in self.storia[(parole*-1) if parole != -1 else 0:]:
            qwndfiu += ((f'<a href="{i.link}">') if link is True else "") + formattaMessaggio(i.text) + ("</a>" if link is True else "") + (" ")
        return qwndfiu.strip()
    
    def everyone_has_written(self):
        for partecipante in self.getAllPartecipants():
            if not partecipante.hasWritten:
                return False
        return True
    
    def lastWordOf(self,userId: str | int):
        for word in self.storia[::-1]:
            if str(word.from_user.id) == str(userId):
                return word
        return None
            
    def wordOfWithId(self, userId: str | int, messageId: str | int):
        userId = str(userId)
        messageId = str(messageId)
        
        for word in self.storia:
            if str(word.message_id) == messageId:
                return word
        return None
    
    def resetTurns(self):
        for user in self.getAllPartecipants():
            user.hasWritten = False
        

def formattaMessaggio(text):
    return text[1:]

#        group_id: Partita
partite: dict[str, Partita] = {}

# #       group_id: storia
# storie: Dict[str, str] = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):  # /start
    
    roba = update.effective_message
    utente = ('@' + roba.from_user.username) if roba.from_user.username != None else roba.from_user.full_name
    idUtente = roba.from_user.id


    users.saveUser(str(idUtente), utente, roba.from_user.language_code)
    cambiaLingua(str(idUtente),users.getUserLang(str(idUtente)))

    logging.info(f'{utente}, {idUtente} - Ha eseguito ' + roba.text)
    
    if "config" in roba.text:
        await prova_messaggio(
            _("Benvenuto nel bot \"One Word Story\". Per configurare riutilizza il comando /cnfg_ows nel gruppo.")
        )
    
    await prova_messaggio(
        _('Benvenuto nel bot "One Word Story". Per giocare aggiungimi in un gruppo e fai /new_ows_game'),
        update=update,
        bot=context.bot
    )

async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    idUtente = update.effective_message.from_user.id
    
    cambiaLingua(str(idUtente),users.getUserLang(str(idUtente)))
    await prova_messaggio(
        _(
            'Questo bot ti permetterà di giocare a OneWordStory nel tuo gruppo!\n\nPer giocarci aggiungilo ad un gruppo e scrivi /new_ows_game. Una volta fatto ciò i giocatori dovranno entrare scrivendo /join_ows_game, e, una volta che tutti saranno pronti, la partita dovrà essere avviata con /start_ows_game da colui che ha creato la partita.\n\nOgni giocatore potrà entrare o uscire da una partita in corso con i comandi /join_ows_game e /quit_ows_game.\n\nA partita avviata, ogni giocatore a turno dovrà scrivere UNA parola preceduta dal carattere "*".\n\nC\'è un tempo di inattività impostato di default a 50 secondi, ma è personalizzabile.\n\nPer modificare le impostazioni del bot è possibile usare il comando /cnfg_ows nella chat del gruppo e configurare le impostazioni desiderate nella chat privata del bot.\n\nPer eventuali problemi contattare @Andtheking.'
        )
    )

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
        
        partite[f'{chat_id}'] = Partita(utente, idUtente,groupId=roba.chat_id, mess=mess) # Crea la partita con l'utente leader (chi l'ha creata)
        
        partite[f'{chat_id}'].partecipanti[f'{idUtente}'] = Partecipante(utente, idUtente) # Aggiungo il creatore ai partecipanti

        logging.info(f'{utente}, {idUtente} - Ha creato una partita nel gruppo {update.message.chat.title}')
    else: # Avviso se la partita è già presente nella lista
        partita = partite[f'{chat_id}']
        await prova_messaggio(
            _('{link_1}Partita già creata{link_2}. Entra con /join_ows_game').format(
                link_1=f'<a href="{partita.MessaggioListaPartecipanti.link[:partita.MessaggioListaPartecipanti.link.rfind("""?""")]}">' if partita.MessaggioListaPartecipanti is not None else "",
                link_2='</a>' if partita.MessaggioListaPartecipanti is not None else ""
            ),
            update = update,
            bot = context.bot
        )

def gameExists(chat_id: int):
    return str(chat_id) in partite

async def join_ows_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global partite
    roba = update.effective_message
    
    # Assegno tutte le variabili per comodità
    # "utente" fa il controllo se l'username è presente altrimenti usa il nome
    utente = roba.from_user.name
    idUtente = str(update.message.from_user.id)
    chat_id = update.message.chat.id

    cambiaLingua(idUtente,users.getUserLang(idUtente))

    # Controllo se per la chat esiste una partita
    if not gameExists(chat_id):
        await prova_messaggio(
            _('Non è stata creata nessuna partita. Creane una con /new_ows_game'),
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
    
    if partita.maxWordsConfig != 0  and len(partita.partecipanti) > partita.maxWordsConfig:
        partita.maxWordsEffective = len(partita.partecipanti)
        await roba.chat.send_message("Ho aggiornato il limite di parole per questa partita a {newMaxWords}.".format(newMaxWords = str(len(partita.partecipanti))))
        
    # Modifica il messaggio di creazione della partita per mostrare la lista dei partecipanti al game

    if partita.MessaggioListaPartecipanti is not None:
        try:
            partite[f'{chat_id}'].MessaggioListaPartecipanti = await context.bot.edit_message_text(
                chat_id = chat_id, 
                message_id = partita.MessaggioListaPartecipanti.message_id, 
                text = partita.MessaggioListaPartecipanti.text + f"\n- {utente}"
            )
        except:
            try:
                await prova_messaggio(
                    partita.MessaggioListaPartecipanti.text + f"\n- {utente}",
                    update=update,
                    bot=context.bot
                )
            except:
                pass
    
    await prova_messaggio(
        _('{user} è entrato nella {link_1}partita{link_2}').format(
            user=utente,
            link_1 = f'<a href="{partita.MessaggioListaPartecipanti.link}">' if partita.MessaggioListaPartecipanti is not None else "",
            link_2 = "</a>" if partita.MessaggioListaPartecipanti is not None else ""
        ),
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
            _('Non è stata creata nessuna partita. Creane una con /new_ows_game'),
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
    
    if partita.maxWordsConfig != 0 and len(partita.partecipanti) > partita.maxWordsConfig:
        partita.maxWordsEffective = len(partita.partecipanti)
        await roba.chat.send_message(_("Ho aggiornato il limite di parole per questa partita a {newMaxWords}.").format(newMaxWords = str(len(partita.partecipanti))))
    
    context.job_queue.run_once(
        callback=test,
        when=partita.timerConfig,
        data=(partita,update),
        name=f"{roba.chat_id} - {partita.aChiTocca().idUtente}"
    )

async def onMessageInGroup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global partite

    roba = update.effective_message
    
    chat_id = roba.chat_id
    utente = roba.from_user.name
    idUtente = str(roba.from_user.id)
    messaggio_id = roba.message_id
    
    users.saveUser(str(idUtente), utente, roba.from_user.language_code) # Il controllo se esiste già è nel metodo direttamente

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
        vecchia_parola = partita.wordOfWithId(userId=idUtente,messageId=roba.message_id)
        if vecchia_parola is not None:
            await prova_messaggio(
                _('Hey {user}, non puoi modificare un messaggio! La parola rimarrà {word}.').format(
                    user=utente,
                    word=formattaMessaggio(
                        vecchia_parola.text
                    )
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
    if not idUtente == partita.aChiTocca().idUtente:
        await prova_messaggio(
            _("{utente}, non è il tuo turno. Tocca a {turno}").format(utente=utente, turno=partita.aChiTocca().nomeUtente),
            update=update,
            bot=context.bot
        )
      
    

    # Se il messaggio contiene uno dei seguenti caratteri avvisa e cancella il messaggio
    if (' ' in messaggio or '_' in messaggio or '-' in messaggio or '+' in messaggio):
        await prova_messaggio(
            _('{utente}, devi scrivere una parola sola :P\nil gioco si chiama "ONE WORD stories" per un motivo.').format(utente=utente),
            update=update,
            bot=context.bot
        )
        return

    max_caratteri = 999

    # Se il messaggio è troppo lungo avvia e cancella il messaggio
    if (len(messaggio) > max_caratteri):
        await prova_messaggio(_(
            '{user}, il messaggio è troppo lungo (più di {max_length})').format(user=utente, max_length=max_caratteri),
            update=update,
            bot=context.bot
        )
    
        return

    partecipante = partita.partecipanti[idUtente]

    
    
    # Se il partecipante ha già scritto avvisa e cancella il messaggio
    if partecipante.hasWritten:
        await prova_messaggio(
            _('{user} hai già scritto una parola.').format(user=utente),
            update=update,
            bot=context.bot
        )
       
        return

    
        
        
    rimuovi_timer(
        roba.chat.id,
        idUtente,
        context.job_queue
    )
    
    partita.addWord(update.effective_message)
    partecipante.hasWritten = True
    
    if partita.skipVotes > 0:
        await prova_messaggio(
            _("Annullata la votazione per skip."),
            update=update,
            bot=context.bot
        )
        partita.resetVotesSkip()
    
    if partita.voteWords > 0:
        await prova_messaggio(
            _("Annullata la votazione per cancellare l'ultima parola."),
            update=update,
            bot=context.bot
        )
        partita.resetVotesCancel()


    if partita.maxWordsConfig != 0 and len(partita.storia) == partita.maxWordsEffective:
        await roba.chat.send_message(
            "Avete raggiunto le " + str(partita.maxWordsEffective) + " parole."
        )
        await termina_partita(
            update=update,
            context=context,
            roba=roba,
            partita=partita,
            chat_id=chat_id
        )
        return

    if partita.everyone_has_written():
        for partecipante in partita.getAllPartecipants():
            partecipante.hasWritten = False
      
        await prova_messaggio(
            _('Tutti i partecipanti hanno scritto una parola. Ora ricominciamo da {user}').format(user=partita.aChiTocca().nomeUtente),
            update=update,
            bot=context.bot
        )

      
    context.job_queue.run_once(
        callback=test, 
        when=partita.timerConfig, 
        data=(partita,update),
        name=f"{roba.chat_id} - {partita.aChiTocca().idUtente}"
    )
    
        
    partita.wakeUpMessages[idUtente] = await prova_messaggio(
        _("Tocca a {user}. Ultime {nWords} parole: {words}").format(
            nWords = partita.wordHistoryConfig,
            user=partita.aChiTocca().nomeUtente,
            words=partita.ottieniStoria(partita.wordHistoryConfig)
        ),
        update=update,
        bot=context.bot
    )
    
    
    
async def test(context: ContextTypes.DEFAULT_TYPE):
    partita: Partita = context.job.data[0]
    update: Update = context.job.data[1]
    
    indiceTurnoAttuale = partita.getAllPartecipants().index(partita.aChiTocca())
    
    await update.effective_message.chat.send_message(
        _("{user} ha impiegato troppo tempo per inviare una parola, skippo il turno a {next}").format(
            user = partita.aChiTocca().nomeUtente,
            next = partita.getAllPartecipants()[(indiceTurnoAttuale + 1) % len(partita.getAllPartecipants())].nomeUtente
        )
    )
    
    partita.resetVotesSkip()
    partita.aChiTocca().hasWritten = True
    
    if partita.everyone_has_written():
        for partecipante in partita.getAllPartecipants():
            partecipante.hasWritten = False
        
        await update.effective_message.chat.send_message(
            _('Tutti i partecipanti hanno scritto una parola. Ora ricominciamo da {user}').format(
                user=partita.aChiTocca().nomeUtente
            )
        )

        context.job_queue.run_once(
            callback=test, 
            when=partita.timerConfig, 
            data=(partita,update),
            name=f"{update.effective_message.chat.id} - {partita.aChiTocca().idUtente}"
        )
        
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
                await context.bot.send_message(chat_id=chat_id,text=_("Partita terminata forzatamente da un admin del bot. Ecco la vostra storia:"))
                await context.bot.send_message(chat_id=chat_id,text=_("#storia\n\n{story}").format(story=capwords(partita.ottieniStoria(link=True), '. ').replace(' .', '.').replace(' ,', ',')))
            else:
                await context.bot.send_message(chat_id=chat_id,text=_("Partita terminata forzatamente da un admin del bot."))
                    
            if str(chat_id) != str(roba.chat_id):
                await prova_messaggio(
                    _("Partita terminata con successo in {group_name}").format(
                        group_name = (await context.bot.get_chat(chat_id)).effective_name
                    ),
                    update=update,
                    bot=context.bot
                )
                # Azzero qualsiasi cosa possibile per cancellare la partita
                    
            for partecipante in partita.getAllPartecipants():
                rimuovi_timer(
                    roba.chat_id,
                    idUtente,
                    context.job_queue
                )
                        
            partite.pop(f'{chat_id}', None)
        return # Non continuo
    
    # Se la partita non esiste non puoi terminarla
    if not f'{chat_id}' in partite:
        await prova_messaggio(_("Devi prima creare una partita."),update=update,bot=context.bot)
        return

    partita = partite[f"{chat_id}"]
    
    # Se non sei il leader della partita o un admin non puoi terminarla
    utenti_che_possono_cancellare: list[ChatMemberAdministrator | ChatMemberOwner] = []
    
    for admin in await update.message.chat.get_administrators():
        admin: ChatMemberAdministrator | ChatMemberOwner
        if type(admin) is ChatMemberAdministrator and admin.can_delete_messages:
            utenti_che_possono_cancellare.append(admin)
        elif type(admin) is ChatMemberOwner:
            utenti_che_possono_cancellare.append(admin)
    
    # Se non è il leader della partita e non è negli admin del gruppo che hanno il potere di cancellare im essaggi
    if (idUtente != partita.leaderId) and (not idUtente in [str(k.user.id) for k in utenti_che_possono_cancellare]):
        await prova_messaggio(_(
            "{utente} non hai avviato tu la partita! Puoi usare /quit_ows_game al massimo").format(
                utente=utente
            ),
            update=update,
            bot=context.bot
        )
        return

    # Se la storia non è vuota la stampi, altrimenti termini la partita e basta
    if (len(partita.storia) > 0):
        await prova_messaggio(_("Termino la partita. Ecco la vostra storia:"),update=update,bot=context.bot)
        await prova_messaggio(_("#storia\n\n{story}").format(story=capwords(partita.ottieniStoria(link=True), '. ').replace(' .', '.').replace(' ,', ',')),update=update,bot=context.bot)
    else:
        await prova_messaggio(_("Termino la partita."),update=update,bot=context.bot)

    # Azzero qualsiasi cosa possibile per cancellare la partita
    
    for partecipante in partita.getAllPartecipants():
        rimuovi_timer(
            roba.chat.id,
            partecipante.idUtente,
            context.job_queue
        )

    partite.pop(f'{chat_id}', None)

async def termina_partita(update: Update, context: ContextTypes.DEFAULT_TYPE, roba: Message, partita: Partita, chat_id: str | int, messaggio: str = None):
    if messaggio is None:
        messaggio = _("Termino la partita.")
        
    # Se la storia non è vuota la stampi, altrimenti termini la partita e basta
    if (len(partita.storia) > 0):
        await prova_messaggio(messaggio + " " + _("Ecco la vostra storia: ").lower(),update=update,bot=context.bot)
        await prova_messaggio(_("#storia\n\n{story}").format(story=capwords(partita.ottieniStoria(link=True), '. ').replace(' .', '.').replace(' ,', ',')),update=update,bot=context.bot)
    else:
        await prova_messaggio(messaggio,update=update,bot=context.bot)

    # Azzero qualsiasi cosa possibile per cancellare la partita
    
    for partecipante in partita.getAllPartecipants():
        rimuovi_timer(
            roba.chat.id,
            partecipante.idUtente,
            context.job_queue
        )

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
        await prova_messaggio(_('Non è stata creata nessuna partita. Creane una con /new_ows_game'),
            update=update,
            bot=context.bot
        )
        return

    partita = partite[f"{chat_id}"]

    # Se l'utente non partecipa alla partita non può quittare lol
    if not idUtente in partita.partecipanti.keys():
        await prova_messaggio(
            _('Non sei in partita!'),
            update=update,
            bot=context.bot
        )
        return

    isHisTurn = False
    if idUtente == partita.aChiTocca().idUtente:
        isHisTurn = True

    # Se il partecipante è l'ultimo
    if len(partita.partecipanti) == 1:
        await termina_partita(
            update=update,
            context=context,
            roba=roba,
            partita=partita,
            chat_id=chat_id,
            messaggio=_("Non è rimasto più nessuno, termino la partita.")
        )
        return

    # Se passi tutti i controlli togli l'utente dai partecipanti e ristampa la lista
    partita.partecipanti.pop(idUtente)

    if partita.maxWordsConfig != 0 and len(partita.partecipanti) > partita.maxWordsConfig:
        partita.maxWordsEffective = len(partita.partecipanti)
        await roba.chat.send_message("Ho aggiornato il limite di parole per questa partita a {newMaxWords}.".format(newMaxWords = str(len(partita.partecipanti))))
    elif partita.maxWordsConfig != 0 and len(partita.partecipanti) == partita.maxWordsConfig:
        partita.maxWordsEffective = partita.maxWordsConfig
        await roba.chat.send_message("La partita può seguire il limite di parole standard impostato nei config ({newMaxWords}).".format(newMaxWords = str(len(partita.partecipanti))))

    rimuovi_timer(
        roba.chat_id,
        idUtente,
        context.job_queue
    )
    
    await prova_messaggio(
        _('{user}, sei uscito dalla partita con successo.\n\nPartecipanti restanti:\n{remain}').format(
            remain = partita.getAllPartecipantsString(), 
            user = update.effective_message.from_user.name
        ),
        update=update,
        bot=context.bot
    )
    
    if isHisTurn:
        await roba.chat.send_message(
            _("Tocca a {user}. Ultime {nWords} parole: {words}").format(
                nWords = partita.wordHistoryConfig,
                user=partita.aChiTocca().nomeUtente,
                words=partita.ottieniStoria(partita.wordHistoryConfig)
            )
        )
        if partita.skipVotes > 0:
            partita.resetVotesSkip()

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

    if idUtente == partita.aChiTocca().idUtente:
        await prova_messaggio(
            _('Non puoi votare per skippare il tuo stesso turno!'),
            update=update,
            bot=context.bot
        )
        return
        

    if partita.skipVotes == 0:  
        partita.skipping = True
        mess = await prova_messaggio(
            (Partita.SKIP_TMPL + ' {voteStatus}/{totalPlayersMinusOne}').format(
                user = utente,
                turn = partita.aChiTocca().nomeUtente, 
                voteStatus = partita.skipVotes,
                totalPlayersMinusOne = partita.getNumberOfPlayers() - 1
            ),
            update=update,
            bot=context.bot
        )
        partita.MessaggioVoteSkip = mess
        
    partita.partecipanti[idUtente].voteSkip = True
    
    if partita.MessaggioVoteSkip is not None:
        await partita.MessaggioVoteSkip.edit_text(
            text = (Partita.SKIP_TMPL + ' {voteStatus}/{totalPlayersMinusOne}').format(
                user = utente,
                turn = partita.aChiTocca().nomeUtente, 
                voteStatus = partita.skipVotes,
                totalPlayersMinusOne = partita.getNumberOfPlayers() - 1
            )
        )
    
    await prova_messaggio(
        text = (_("{user} ha votato per lo skip.") + ' {voteStatus}/{totalPlayersMinusOne}').format(
            user=roba.from_user.name,
            voteStatus=partita.skipVotes,
            totalPlayersMinusOne=partita.getNumberOfPlayers() - 1
        ),
        update=update,
        bot=context.bot
    )

    if partita.skipVotes >= partita.getNumberOfPlayers() - 1:
        voti_attuali = partita.skipVotes
        player_totali = partita.getNumberOfPlayers()
        await prova_messaggio(
            _('{voteStatus} voti di {totalPlayersMinusOne}, skip confermato.').format(
                voteStatus = voti_attuali,
                totalPlayersMinusOne = player_totali - 1
            ),
            update=update,
            bot=context.bot
        )
        partita.partecipanti[f"{partita.aChiTocca().idUtente}"].hasWritten = True

        rimuovi_timer(
            roba.chat.id,
            idUtente,
            context.job_queue
        )

        for partecipante in partita.getAllPartecipants():
            partecipante.voteSkip = False
        
        if partita.everyone_has_written():
            partita.resetTurns()
            
            await prova_messaggio(
                _('Tutti i partecipanti hanno scritto una parola. Ora ricominciamo da {turno}.\n\nUltime {nWords} parole: {words}').format(
                    nWords=partita.wordHistoryConfig,
                    turno=partita.getAllPartecipants()[0].nomeUtente,
                    words=partita.ottieniStoria(partita.wordHistoryConfig)
                ),
                update=update,
                bot=context.bot
            )

def rimuovi_timer(chatId,idUtente, job_queue: JobQueue):
    chatId = str(chatId)
    idUtente = str(idUtente)
    
    current_jobs = job_queue.get_jobs_by_name(f"{chatId} - {idUtente}")
    if current_jobs:
        for job in current_jobs:
            job.schedule_removal()

async def wakeUp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global partite

    # Solito copia incolla
    roba = update.effective_message
        
    utente = roba.from_user.name
    idUtente = str(roba.from_user.id)
    chat_id = roba.chat.id
    messaggio = roba.text
    messaggio_id = roba.message_id

    cambiaLingua(str(idUtente),users.getUserLang(str(idUtente)))

    # Se la partita non esiste
    if not f'{chat_id}' in partite:
        await prova_messaggio(
            _("Devi prima partecipare ad una partita."),
            update=update,
            bot=context.bot
        )
        return

    # Se la partita è avviata
    if not partite[f'{chat_id}'].isStarted:
        await prova_messaggio(_("Partita non avviata"),update=update,
                    bot=context.bot)
        return

    await prova_messaggio(
        _("Sveglia {turn}, tocca a te!").format(
            turn=partite[f'{chat_id}'].aChiTocca().nomeUtente
        ),
        update=update,bot=context.bot
    )


# Segnala quando il bot crasha, con motivo del crash
async def error(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.warning('Update "%s" caused error "%s"', update, context.error)
    await context.bot.send_message(ID_CANALE_LOG, text=f'{context.bot.name}\nUpdate "{update}" caused error "{context.error}')

# TODO: Guardarci meglio, aggiustare un po'
async def lingua(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await prova_messaggio("To be translated...\n\nWanna translate the bot in your language? Ask @Andtheking!",update=update, bot=context.bot)
    return
    
    keyboard = [
        [
            InlineKeyboardButton("Italiano", callback_data="language:Italiano,it"),
            InlineKeyboardButton("English", callback_data="language:English,en"),
        ]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await prova_messaggio("Select a language",reply_markup=reply_markup,update=update,
                    bot=context.bot)

async def linguaPremuta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # TODO: RENDERE ALMENO "CARINO"
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(text=f"Chosen language: {query.data.split(',')[0]}")
    
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

CONFIG_KEYBOARD = [
        [
            InlineKeyboardButton(_("Attesa per skip"), callback_data="config:attesa_skip"),
            InlineKeyboardButton(_("Numero parole di recap"), callback_data="config:parole_recap"),
        ],
        [
            InlineKeyboardButton(_("Max parole partita"), callback_data="config:max_parole")
        ],
    ]

async def config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    
    message = update.effective_message
    
    chat_id = message.chat_id
    
    if chat_id > 0:
        await message.reply_text(_("Usa questo comando in un gruppo in cui hai il permesso di modificare le informazioni del gruppo."))
        return
    
    if message.from_user.id != 245996916:
        utenti_ammessi: list[User] = []
        for admin in await update.message.chat.get_administrators():
            admin: ChatMemberAdministrator | ChatMemberOwner
            if type(admin) is ChatMemberAdministrator and admin.can_change_info:
                utenti_ammessi.append(admin.user)
            elif type(admin) is ChatMemberOwner:
                utenti_ammessi.append(admin.user)
        
        if message.from_user.id not in [u.id for u in utenti_ammessi]:
            await prova_messaggio(
                _("Non hai il permesso di modificare le informazioni del gruppo, quindi neanche le impostazioni di questo bot."),
                update=update,
                bot=context.bot
                )
            return
    
    try:
        gc = groupsConfig()
        if not str(update.message.chat_id) in gc:
            gc[update.message.chat_id] = fromJSON("defaultConfig.json")
            toJSON("groupsConfig.json",gc)
        
        await context.bot.send_message(
            update.message.from_user.id,
            _('Ecco le impostazioni delle partite nel gruppo {link}').format(link=f'<a href="{message.chat.link}">{message.chat.effective_name}</a>'),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(CONFIG_KEYBOARD)
        )
        
        await prova_messaggio(
            messaggio=_("Vai in privato per le impostazioni del gruppo!"),
            update=update,
            bot=context.bot,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Apri chat",url=context.bot.link)]])
        )
        
        context.user_data['message'] = message
        context.user_data['group_chat'] = message.chat
    except:
        await prova_messaggio(
            _('Devi prima avviare il bot in privato!'),
            update=update,
            bot=context.bot,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(_('Avviami in privato!'),url=context.bot.link + "?start=config")]])
        )
    
async def config_skiptime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Teoricamente qui siamo in chat privata per forza
    
    query = update.callback_query
    gc = groupsConfig()
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=_("Inviami quanti secondi vuoi impostare di attesa prima di saltare un turno per inattività. Valore attuale: {value}").format(value = gc[str(context.user_data['group_chat'].id)]['skiptime'] if str(context.user_data['group_chat'].id) in gc else "NONE?")
    )
    
    await query.answer()
    return 1

keyboard_go_back = InlineKeyboardMarkup(
    [
        [
            InlineKeyboardButton('Torna alla lista',callback_data='config:go_back')
        ]
    ]
)

async def backToConfig(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message: Message = context.user_data['message']
    toEdit: Message = context.user_data['messageToEdit']
    
    await toEdit.edit_text(
        text=_('Ecco le impostazioni delle partite nel gruppo {link}').format(link=f'<a href="{message.chat.link}"><b>{message.chat.effective_name}</b></a>'),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(CONFIG_KEYBOARD)
    )
    
    context.user_data['messageToEdit'] = None
    await update.callback_query.answer()


async def configSave_skiptime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mex = update.effective_message
    txt = mex.text.strip()
    
    
    if not txt.isnumeric():
        await update.effective_message.reply_text(_('Il messaggio deve essere solo un numero (esempio: "50") e rappresenterà il numero di secondi che aspetterò prima di skippare un turno. Riprova o annulla con /cancel.'))
        return 
    gc = groupsConfig()
    
    gc[str(context.user_data['group_chat'].id)]['skiptime'] = int(txt)
    toJSON("groupsConfig.json",gc)
    
    context.user_data['messageToEdit'] = await update.effective_message.reply_text(
        _("Tempo di inattività aggiornato a {newValue} per il gruppo {group}.")
        .format(
            newValue=groupsConfig()[str(context.user_data['group_chat'].id)]['skiptime'],
            group=context.user_data['group_chat'].title
        ),
        reply_markup=keyboard_go_back
    )
    
    
    return ConversationHandler.END

async def config_recapwords(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    gc = groupsConfig()
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=_("Inviami ora quante parole dovrò mostrare per il recap (0 nessuna, -1 tutta la storia). Valore attuale: {value}").format(
            value=gc[str(context.user_data['group_chat'].id)]['wordHistory'] if str(context.user_data['group_chat'].id) in gc else "NONE?"
        )
    )
    
    await query.answer()
    return 1    

async def configSave_recapwords(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mex = update.effective_message
    txt = mex.text.strip()
    
    if txt != "-1" and not txt.isnumeric():
        await update.effective_message.reply_text(_('Il messaggio deve essere solo un numero (esempio: "6") e rappresenterà il numero di parole che scriverò ogni turno (-1 tutta la storia, 0 nessun recap). Riprova o annulla con /cancel.'))
        return 
    
    gc = groupsConfig()
    gc[str(context.user_data['group_chat'].id)]['wordHistory'] = int(txt)
    toJSON("groupsConfig.json",gc)
    
    context.user_data['messageToEdit'] = await update.effective_message.reply_text(
        _("Parole di recap aggiornate a {newValue} per il gruppo {group}.")
        .format(
            newValue=groupsConfig()[str(context.user_data['group_chat'].id)]['wordHistory'],
            group=context.user_data['group_chat'].title
        ),
        reply_markup=keyboard_go_back
    )
    
    return ConversationHandler.END

async def config_maxwords(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=_("Inviami ora quante parole durerà la partita (0: nessun limite).\nSe imposti un numero di parole troppo basso il bot imposterà il massimo di parole per ogni partita al doppio del numero di partecipanti (work in progress, per ora segue questo massimo). Valore attuale: {value}").format(value = groupsConfig[str(context.user_data['group_chat'].id)]['maxWords'] if str(context.user_data['group_chat'].id) in groupsConfig else "NONE?") # TODO: Riguardare questo punto
    )
    
    await query.answer()
    return 1    

async def configSave_maxwords(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mex = update.effective_message
    txt = mex.text.strip()
    
    if not txt.isnumeric():
        await update.effective_message.reply_text(_('Il messaggio deve essere solo un numero (esempio: "30") e rappresenterà il numero di parole massime per una storia (essenzialmente la durata di una partita). Riprova o annulla con /cancel.'))
        return
    
    gc = groupsConfig()
    gc[str(context.user_data['group_chat'].id)]['maxWords'] = int(txt)
    toJSON("groupsConfig.json",gc)
    
    context.user_data['messageToEdit'] = await update.effective_message.reply_text(
        _("Parole massime aggiornate a {newValue} per il gruppo {group}.")
        .format(
            newValue=groupsConfig()[str(context.user_data['group_chat'].id)]['maxWords'],
            group=context.user_data['group_chat'].title
        ),
        reply_markup=keyboard_go_back
    )
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_message.chat_id, text="Azione cancellata.")
    return ConversationHandler.END

async def onJoin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        if member.username == context.bot.username:
            gc = groupsConfig()
            if not update.message.chat_id in gc:
                gc[update.message.chat_id] = fromJSON("defaultConfig.json")
                toJSON("groupsConfig.json",gc)
            else:
                await context.bot.send_message(update.message.chat_id, "Ciao! Questo gruppo aveva già una configurazione salvata in passato, utilizzerò quella.")

async def vote_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global partite

    roba = update.effective_message
        
    nomeUtente = roba.from_user.name
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
        return

    if not idUtente in partita.partecipanti.keys():
        await prova_messaggio(
            _("{user}, non sei in partita.").format(user=nomeUtente),
            update=update, 
            bot=context.bot
        )
        return
        
    if partita.partecipanti[str(idUtente)].voteWord:
        await prova_messaggio(
            _("{user}, hai già votato.").format(user=nomeUtente),
            update=update, 
            bot=context.bot
        )
        return

    partita.voteWords += 1
    partita.partecipanti[str(idUtente)].voteWord = True
    
    if partita.voteWords == 1:
        await prova_messaggio(
            _("Il giocatore {utente} ha avviato la votazione per annullare l'ultima parola giocata, votate con /cancel_ows_word. Stato votazione: {votes}/{votesNeeded}\n\nSe {turn} scriverà una parola la votazione sarà annullata.").format(
                utente = nomeUtente,
                votes = partita.voteWords,
                votesNeeded = len(partita.partecipanti),
                turn = partita.aChiTocca().nomeUtente
            ),
            update=update,
            bot=context.bot
        )
    else:
        await prova_messaggio(
            _("{utente} ha votato per annullare l'ultima parola giocata, votate con /cancel_ows_word. Stato votazione: {votes}/{votesNeeded}").format(
                utente = nomeUtente,
                votes = partita.voteWords,
                votesNeeded = len(partita.partecipanti)
            ),
            update=update,
            bot=context.bot
        )

    if partita.voteWords == len(partita.partecipanti):
        rimossa = partita.storia.pop()
        rimuovi_timer(
            chatId=chat_id,
            idUtente=partita.aChiTocca().idUtente,
            job_queue = context.job_queue
        )
        partita.getLastTurn().hasWritten = False
        
        await prova_messaggio(
            _("La votazione per annullare l'ultima parola giocata ({word}) ha avuto successo.\n\nTocca di nuovo a {user}, Ultime {nWords} parole: {words}").format(
                word = formattaMessaggio(rimossa.text.strip()),
                user = partita.aChiTocca().nomeUtente,
                nWords = partita.wordHistoryConfig,
                words=partita.ottieniStoria(partita.wordHistoryConfig)
            ),
            update=update,
            bot=context.bot
        )
        
        context.job_queue.run_once(
            callback=test, 
            when=partita.timerConfig, 
            data=(partita,update),
            name=f"{roba.chat_id} - {partita.aChiTocca().idUtente}"
        )
        
        partita.resetVotesCancel()


   

def main():
    # Avvia il bot

    # Crea l'Updater e passagli il token del tuo bot
    # Accertati di impostare use_context=True per usare i nuovi context-based callbacks (non so cosa siano)
    # Dalla versione 12 non sarà più necessario
    application = Application.builder().token(TOKEN).persistence(PicklePersistence(filepath="salvataggio_bot",update_interval=1)).build() # Se si vuole usare la PicklePersistance bisogna aggiungere dopo .token(TOKEN) anche .persistance(OGGETTO_PP)

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("new_ows_game", crea_partita))
    application.add_handler(CommandHandler("join_ows_game", join_ows_game))
    application.add_handler(CommandHandler("start_ows_game", avvia_partita))
    application.add_handler(CommandHandler("end_ows_game", end_game))
    application.add_handler(CommandHandler("quit_ows_game", quit_ows_game))
    application.add_handler(CommandHandler("skip_ows_turn",skip_turn))
    application.add_handler(CommandHandler("wakeUp_ows",wakeUp))
    
    application.add_handler(CommandHandler("cnfg_ows",config))
    application.add_handler(CallbackQueryHandler(backToConfig,pattern='config:go_back'))
    
    application.add_handler(
        ConversationHandler(
            entry_points=[CallbackQueryHandler(config_skiptime, pattern="config:attesa_skip")],
            states={
                1: [MessageHandler(~filters.COMMAND, configSave_skiptime)]
            },
            fallbacks=[CommandHandler('cancel',cancel)],
            persistent=True,
            name='AttesaSkip'
        )
    )
    
    application.add_handler(
        ConversationHandler(
            entry_points=[CallbackQueryHandler(config_recapwords, pattern="config:parole_recap")],
            states={
                1: [MessageHandler(~filters.COMMAND, configSave_recapwords)]
            },
            fallbacks=[CommandHandler('cancel',cancel)],
            persistent=True,
            name='ParoleRecap'
        )
    )
    
    application.add_handler(
        ConversationHandler(
            entry_points=[CallbackQueryHandler(config_maxwords, pattern="config:max_parole")],
            states={
                1: [MessageHandler(~filters.COMMAND, configSave_maxwords)]
            },
            fallbacks=[CommandHandler('cancel',cancel)],
            persistent=True,
            name='MaxParole'
        )
    )
    
    application.add_handler(CommandHandler("changeLanguage_ows",lingua))
    application.add_handler(CallbackQueryHandler(linguaPremuta, pattern="language"))

    application.add_handler(
        MessageHandler(
            filters.StatusUpdate.NEW_CHAT_MEMBERS, callback=onJoin
        )
    )

    # Legge i messaggi dei gruppi e supergruppi ma non i comandi, per permettere /end_game e /quit_ows_game
    application.add_handler( 
        MessageHandler(
            filters.ChatType.GROUPS & 
            filters.TEXT &
            ~filters.COMMAND, onMessageInGroup, block=False)
        ) 
    
    application.add_handler(
        CommandHandler(
            "cancel_ows_word",
            callback=vote_word
        )
    )
    
    application.add_handler(
        CommandHandler(
            "help",
            callback=help
        )
    )

    # In caso di errore vai nel metodo "error"
    application.add_error_handler(error)

    # Avvia il bot con il polling
    application.run_polling()


# Se avvii il programma direttamente va qui, altrimenti se lo usi tipo come libreria no
if __name__ == '__main__':
    main()
