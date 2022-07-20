import logging # Per loggare (non si usa "print()" ma logger.info())
import requests  # Per mandare la richiesta di invio messaggio quando online

from string import capwords
from typing import Dict
from time import sleep

from telegram import (
    Update, # È il tipo che usiamo nelle funzioni
    Message, # Il tipo per i messaggi
)
from telegram.ext import (
    Updater, # Per il bot
    CommandHandler, # Per i comandi
    CallbackContext, # Tipo del parametro "context" di tutti i metodi
    MessageHandler, # Per i messaggi
    Filters, # Per i messaggi (i filtri tipo per dire: Agisci quando ricevi immagini, file, audio, tutto e cose così)
)


TOKEN = None  # TOKEN DEL BOT
with open('token.txt', 'r') as f:
    TOKEN = f.read().strip()

# ID TELEGRAM PER RICEVERE NOTIFICA (ottienilo con t.me/JsonDumpBot)
ID_OWNER = "245996916"

# https://docs.python-telegram-bot.org/en/stable/telegram.ext.handler.html

# Questa è la configurazione di base del log, io lo lascio così di solito
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)


# Rappresenta un partecipante alla partita:
#   nomeUtente: Il suo username o nome e cognome
#   idUtente: Il suo id
#   hasWritten: Se ha già scritto una parola o no
class Partecipante:
    def __init__(self, username, id) -> None:
        self.nomeUtente = username
        self.idUtente = id
        self.hasWritten = False


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
        self.leaderId: str = userId
        self.partecipanti: Dict[str, Partecipante] = {}
        self.isStarted: bool = False
        self.MessaggioListaPartecipanti: Message = mess

    def getAllPartecipantsIDs(self) -> list[str]:
        return list(self.partecipanti.keys())

    def getAllPartecipants(self, stringa: bool = False) -> list[str] | str:
        lista = []

        for partecipante in self.getAllPartecipantsIDs():
            lista.append(self.partecipanti[partecipante].nomeUtente)

        if not stringa:
            return lista

        listaStringa = ''
        
        for partecipante in lista:
            listaStringa += partecipante + '\n'
        
        return listaStringa

    def prossimoTurno(self) -> Partecipante:
        for partecipante in self.getAllPartecipantsIDs():
            if not self.partecipanti[partecipante].hasWritten:
                return self.partecipanti[partecipante]


#        group_id: Partita
partite: Dict[str, Partita] = {}

#       group_id: storia
storie: Dict[str, str] = {}

def start(update: Update, context: CallbackContext):  # /start
    utente = update.message.from_user.username if update.message.from_user.username != None else update.message.from_user.full_name
    idUtente = update.message.from_user.id

    logging.info(f'{utente}, {idUtente} - Ha eseguito /start')
    update.message.reply_text(
        f'Benvenuto nel bot "One Word Story". Per giocare aggiungimi in un gruppo COME AMMINISTRATORE e fai /crea_partita')


def crea_partita(update: Update, context: CallbackContext):
    global partite

    # Assegno tutte le variabili per comodità
    utente = update.message.from_user.username if update.message.from_user.username != None else update.message.from_user.full_name
    idUtente = update.message.from_user.id

    chat_id = update.message.chat.id

    # Controllo se la chat è una chat privata, se sì esce dalla funzione
    if chat_id > 0:
        update.message.reply_text(
            f'Hey {utente}, non vorrai mica giocare da solo? Usa questo comando in un gruppo')
        return

    # Se la chat non è presente nella lista delle partite
    if not f'{chat_id}' in partite:
        mess = update.message.reply_text(
            f'{utente} ha creato una partita. Entra con /join_ows_game.\n\nPartecipanti:\n- {utente}')
        partite[f'{chat_id}'] = Partita(utente, idUtente, mess=mess) # Crea la partita con l'utente leader (chi l'ha creata)
        storie[f'{chat_id}'] = '' # Inizializzo la variabile storie per la chat a cui andrò a concatenare le varie parole
        partite[f'{chat_id}'].partecipanti[f'{idUtente}'] = Partecipante(
            utente, idUtente) # Aggiungo il creatore ai partecipanti
        logging.info(f'{utente}, {idUtente} - Ha creato una partita nel gruppo {update.message.chat.title}')
    else: # Avviso se la partita è già presente nella lista
        update.message.reply_text(
            f'Partita già creata. Entra con /join_ows_game')



def join_ows_game(update: Update, context: CallbackContext):
    global partite

    # Assegno tutte le variabili per comodità
    # "utente" fa il controllo se l'username è presente altrimenti usa il nome
    utente = update.message.from_user.username if update.message.from_user.username != None else update.message.from_user.full_name
    idUtente = update.message.from_user.id
    chat_id = update.message.chat.id


    # Controllo se per la chat esiste una partita
    if not f'{chat_id}' in partite:
        update.message.reply_text(
            f'Non è stata creata nessuna partita. Creane una con /crea_partita')
        return

    # Controllo se l'utente è già nella lista dei partecipanti della partita
    if str(idUtente) in partite[f'{chat_id}'].partecipanti:
        update.message.reply_text(f'Partecipi già alla partita!')
        return


    # Creo il nuovo partecipante
    partite[f'{chat_id}'].partecipanti[f'{idUtente}'] = Partecipante(
        utente, idUtente)
    
    # Modifica il messaggio di creazione della partita per mostrare la lista dei partecipanti al game
    partite[f'{chat_id}'].MessaggioListaPartecipanti = context.bot.edit_message_text(
        chat_id=chat_id, message_id=partite[f'{chat_id}'].MessaggioListaPartecipanti.message_id, text=partite[f'{chat_id}'].MessaggioListaPartecipanti.text + f"\n- {utente}")

    update.message.reply_text(f'{utente} è entrato nella partita')

def avvia_partita(update: Update, context: CallbackContext):
    global partite

    # Solite variabili per comodità
    utente = update.message.from_user.username if update.message.from_user.username != None else update.message.from_user.full_name
    idUtente = update.message.from_user.id
    chat_id = update.message.chat.id

    # Se la partita non esiste
    if not f'{chat_id}' in partite: 
        update.message.reply_text(
            f'Non è stata creata nessuna partita. Creane una con /crea_partita')
        return

    # Se un utente che non è il creatore prova ad avviare la partita, non può
    if not idUtente == partite[f'{chat_id}'].leaderId:
        update.message.reply_text("Non hai creato tu la partita")
        return

    # Controlla se la partita è già avviata
    if partite[f'{chat_id}'].isStarted:
        update.message.reply_text("Partita già avviata")
        return

    # Se tutti i controlli sono andati a buon fine, avvia la partita
    partite[f'{chat_id}'].isStarted = True 

    update.message.reply_text(
        f"{utente} ha avviato la partita. Da ora cancellerò tutti i messaggi dei partecipanti che:\n - Non contengono una parola sola;\n - Hanno già scritto una parola.\n\nL'ordine dei turni è:\n"+partite[f'{chat_id}'].getAllPartecipants(True))


# Questo metodo è avviato asincrono per poter usare sleep per cancellare i messaggi dopo tot secondi
def onMessageInGroup(update: Update, context: CallbackContext):
    global partite

    # Variabili per comodità
    # Ora tutte queste variabili hanno un controllo in più,
    # questo per evitare errori in caso il messaggio ricevuto sia
    # un messaggio modificato e non un messaggio nuovo.
    # (Se il messaggio è modificato l'update sarà edited_message e non message)
    chat_id = update.message.chat.id if update.message != None else update.edited_message.chat.id
    utente = (update.message.from_user.username if update.message.from_user.username != None else update.message.from_user.full_name) if update.message != None else (
    update.edited_message.from_user.username if update.edited_message.from_user.username != None else update.edited_message.from_user.full_name)
    idUtente = update.message.from_user.id if update.message != None else update.edited_message.from_user.id
    messaggio_id = update.message.message_id if update.message != None else update.edited_message

    # Se la partita non esiste o non è stata avviata non fare nulla
    if (not f'{chat_id}' in partite) or (not partite[f'{chat_id}'].isStarted):
        return

    # Se l'utente non è in partita, non fare nulla
    if not str(idUtente) in partite[f'{chat_id}'].getAllPartecipantsIDs():
        return
    
    # Se il messaggio è modificato, non aggiornare la storia
    if update.edited_message != None:
        update.edited_message.reply_text(
            f'Hey {utente}, non puoi modificare un messaggio! La tua parola rimarrà: {storie[f"{chat_id}"].split(" ")[-2]}')
        return


    messaggio = update.message.text 

    
    # Se non è il turno dell'utente avvisa e cancella il messaggio
    if not idUtente == partite[f'{chat_id}'].prossimoTurno().idUtente:
        messaggioDaCancellare = update.message.reply_text(
            f"{utente}, non è il tuo turno. Tocca a {partite[f'{chat_id}'].prossimoTurno().nomeUtente}")
        context.bot.delete_message(chat_id, messaggio_id)
        sleep(3)
        context.bot.delete_message(chat_id, messaggioDaCancellare.message_id)
        return
    
    

    # Se il messaggio contiene uno dei seguenti caratteri avvisa e cancella il messaggio
    if (' ' in messaggio or '_' in messaggio or '-' in messaggio or '+' in messaggio):
        messaggioDaCancellare = update.message.reply_text(
            f'{utente}, devi scrivere una parola sola :P\nil gioco si chiama "ONE WORD stories" per un motivo.')
        context.bot.delete_message(chat_id, messaggio_id)
        sleep(3)
        context.bot.delete_message(chat_id, messaggioDaCancellare.message_id)
        return

    max_caratteri = 15

    # Se il messaggio è troppo lungo avvia e cancella il messaggio
    if (len(messaggio) > max_caratteri):
        messaggioDaCancellare = update.message.reply_text(
            f'{utente}, il messaggio è troppo lungo (più di {max_caratteri})')
        context.bot.delete_message(chat_id, messaggio_id)
        sleep(3)
        context.bot.delete_message(chat_id, messaggioDaCancellare.message_id)
        return

    partecipante = partite[f'{chat_id}'].partecipanti[str(idUtente)]

    # Se il partecipante ha già scritto avvisa e cancella il messaggio
    if partecipante.hasWritten:
        messaggioDaCancellare = update.message.reply_text(
            f'{utente} hai già scritto una parola.')
        context.bot.delete_message(chat_id, messaggio_id)
        sleep(3)
        context.bot.delete_message(chat_id, messaggioDaCancellare.message_id)
        return


    storie[str(chat_id)] += messaggio + ' ' # Aggiungi il messaggio alla storia 
                                            # (avrei potuto mettere la stringa dentro il dictionary partite
                                            #  ma ora non ho voglia di cambiare tutto)
    
    partecipante.hasWritten = not partecipante.hasWritten # Inverto la sua proprietà hasWritten (quindi diventa true)

    # Se hanno scritto tutti, metti a tutti "hasWritten = false"
    if all_partecipants_have_written(partite[f'{chat_id}']):
        for id in partite[f'{chat_id}'].getAllPartecipantsIDs():
            partite[f'{chat_id}'].partecipanti[f'{id}'].hasWritten = False

        messaggioDaCancellare = update.message.reply_text(
            f'Tutti i partecipanti hanno scritto una parola. Ora potete riscrivere')
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
    utente = update.message.from_user.username if update.message.from_user.username != None else update.message.from_user.full_name
    idUtente = update.message.from_user.id
    chat_id = update.message.chat.id
    messaggio = update.message.text
    messaggio_id = update.message.message_id


    # Se la partita non esiste non puoi terminarla
    if not f'{chat_id}' in partite:
        update.message.reply_text("Devi prima creare una partita.")
        return

    # Se non sei il leader della partita non puoi terminarla
    if not idUtente == partite[f'{chat_id}'].leaderId:
        update.message.reply_text(
            f"{utente} non hai avviato tu la partita! Puoi usare /quit_ows_game al massimo")
        return

    # Se la storia non è vuota la stampi, altrimenti termini la partita e basta
    if (storie[f'{chat_id}'] != ""):
        update.message.reply_text("Termino la partita. Ecco la vostra storia:")
        update.message.reply_text(capwords(storie[f'{chat_id}'], '. '))
    else:
        update.message.reply_text("Termino la partita.")

    # Azzero qualsiasi cosa possibile per cancellare la partita
    partite.pop(f'{chat_id}', None)
    storie.pop(f'{chat_id}', None)

def quit_ows_game(update: Update, context: CallbackContext):
    global partite

    # Solito copia incolla
    utente = update.message.from_user.username if update.message.from_user.username != None else update.message.from_user.full_name
    idUtente = update.message.from_user.id
    chat_id = update.message.chat.id
    messaggio = update.message.text
    messaggio_id = update.message.message_id

    # Se non esiste una partita non puoi quittarla e.e
    if not f'{chat_id}' in partite:
        update.message.reply_text(
            f'Non è stata creata nessuna partita. Creane una con /crea_partita')
        return

    # Se l'utente non partecipa alla partita non può quittare lol
    if not str(idUtente) in partite[f'{chat_id}'].partecipanti:
        update.message.reply_text(f'Non sei in partita!')
        return

    # Se passi tutti i controlli togli l'utente dai partecipanti e ristampa la lista
    partite[f'{chat_id}'].partecipanti.pop(str(idUtente))
    update.message.reply_text(f"Sei uscito dalla partita con successo.\n\nPartecipanti restanti:\n{partite[f'{chat_id}'].getAllPartecipants(True)}")

# Segnala quando il bot crasha, con motivo del crash
def error(update: Update, context: CallbackContext):
    logger.warning('Update "%s" caused error "%s"', update, context.error)

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

    dp.add_handler(MessageHandler(Filters.chat_type.groups & ~
                   Filters.command, onMessageInGroup, run_async=True)) # Legge i messaggi dei gruppi e supergruppi ma non i comandi, per permettere /end_game e /quit_ows_game

    
    # Questo per ricevere una notifica quando il bot è online; utile all'inizio, dopo disattivalo sennò impazzisci per le notifiche
    # requests.post(
    #     f"https://api.telegram.org/bot{TOKEN}/sendMessage?chat_id={ID_OWNER}&text=Bot online")

    # In caso di errore vai nel metodo "error"
    dp.add_error_handler(error)

    # Avvia il bot con il polling
    updater.start_polling()

    # Con idle avvii il bot finché non premi CTRL-C o il processo riceve "SIGINT", "SIGTERM" o "SIGABRT".
    # Questo dovrebbe essere usato la maggior parte del tempo, in quanto start_polling() non è bloccante e interromperà il bot.
    updater.idle()


# Questa roba è tipo standard di Python, non so che cazzo sia ma so che serve ad avviare il programma.
if __name__ == '__main__':
    main()
