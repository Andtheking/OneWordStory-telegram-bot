TOKEN = None # TOKEN DEL BOT

with open('token.txt','r') as f:
    TOKEN = f.read().strip()

ID_OWNER = "245996916" # ID TELEGRAM PER RICEVERE NOTIFICA (ottienilo con t.me/JsonDumpBot)

# https://docs.python-telegram-bot.org/en/stable/telegram.ext.handler.html

from email import message
from queue import Empty
from time import sleep

from telegram.ext import (
    Updater, # Per il bot
    CommandHandler, # Per i comandi
    CallbackContext, # idk
    MessageHandler, # Per i messaggi
    Filters, # Per i messaggi (i filtri tipo per dire: Agisci quando ricevi immagini, file, audio, tutto e cose così)
    ConversationHandler, # Per più comandi concatenati
)


from typing import Dict

from telegram import (
    Update, # È il tipo che usiamo nelle funzioni
    Message,
)

from string import capwords

import requests # Per mandare la richiesta di invio messaggio quando online
import logging # Per loggare (non si usa "print()" ma logger.info())

# Questa è la configurazione di base del log, io lo lascio così di solito
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

class Partecipante:
    def __init__(self, username, numero) -> None:
        self.numero = numero
        self.nomeUtente = username
        self.hasWritten = False

class Partita:
    def __init__(self, utente, userId, mess)-> None:
        self.whoCreated: str = utente
        self.whoCreatedId: str = userId
        self.partecipanti: Dict[str,Partecipante] = {}
        self.isStarted: bool = False
        self.turno: int = 0
        self.MessaggioListaPartecipanti: Message = mess


    def getAllPartecipantsIDs(self) -> list[str]:
        return list(self.partecipanti.keys())

    def prossimoTurno(self) -> Partecipante:
        for partecipante in self.getAllPartecipantsIDs():
            if not self.partecipanti[partecipante].hasWritten:
                return self.partecipanti[partecipante]
    
    def ottieniUltimoNumeroGiocatore(self) -> int:
        return self.partecipanti[list(self.partecipanti.keys())[-1]].numero


#        group_id: Partita()
partite: Dict[str,Partita] = {}

#       group_id: storia
storie: Dict[str,str] = {}


def start(update: Update, context: CallbackContext): # /start
    utente = update.message.from_user.username if update.message.from_user.username != None else update.message.from_user.full_name
    idUtente = update.message.from_user.id
    
    logging.info(f'{utente}, {idUtente} - Ha eseguito /start')
    update.message.reply_text(f'Benvenuto nel bot "One Word Story". Per giocare aggiungimi in un gruppo COME AMMINISTRATORE e fai /crea_partita')


def crea_partita(update: Update, context: CallbackContext):
    global partite
    
    utente = update.message.from_user.username if update.message.from_user.username != None else update.message.from_user.full_name
    idUtente = update.message.from_user.id

    chat_id = update.message.chat.id

    if chat_id > 0:
        update.message.reply_text(f'Hey {utente}, non vorrai mica giocare da solo? Usa questo comando in un gruppo')
        return
    
    if not f'{chat_id}' in partite:
        mess = update.message.reply_text(f'{utente} ha creato una partita. Entra con /join_ows_game.\n\nPartecipanti:\n- {utente}')
        partite[f'{chat_id}'] = Partita(utente, idUtente, mess=mess)
        storie[f'{chat_id}'] = '' 
        partite[f'{chat_id}'].partecipanti[f'{idUtente}'] = Partecipante(utente,0)
    else: 
        update.message.reply_text(f'Partita già creata. Entra con /join_ows_game')


def join_ows_game(update: Update, context: CallbackContext):
    global partite

    utente = update.message.from_user.username if update.message.from_user.username != None else update.message.from_user.full_name
    idUtente = update.message.from_user.id
    chat_id = update.message.chat.id
    
    if not f'{chat_id}' in partite:
        update.message.reply_text(f'Non è stata creata nessuna partita. Creane una con /crea_partita')
        return

    if str(idUtente) in partite[f'{chat_id}'].partecipanti:
        update.message.reply_text(f'Partecipi già alla partita!')
        return


    partite[f'{chat_id}'].partecipanti[f'{idUtente}'] = Partecipante(utente, partite[f'{chat_id}'].ottieniUltimoNumeroGiocatore() + 1)
    context.bot.edit_message_text(chat_id=chat_id, message_id=partite[f'{chat_id}'].MessaggioListaPartecipanti.message_id, text=partite[f'{chat_id}'].MessaggioListaPartecipanti.text + f"\n- {utente}")

    logger.info(f"Partecipanti alla partita:")
    

    for partecipante in partite[f'{chat_id}'].partecipanti:
        logger.info(f"{partecipante} ({partite[f'{chat_id}'].partecipanti[f'{partecipante}'].nomeUtente})")


    update.message.reply_text(f'{utente} è entrato nella partita')

def avvia_partita(update: Update, context: CallbackContext):
    global partite
    
    utente = update.message.from_user.username if update.message.from_user.username != None else update.message.from_user.full_name
    idUtente = update.message.from_user.id
    chat_id = update.message.chat.id

    if not f'{chat_id}' in partite:
        update.message.reply_text(f'Non è stata creata nessuna partita. Creane una con /crea_partita')
        return

    if not idUtente == partite[f'{chat_id}'].whoCreatedId:
        update.message.reply_text("Non hai creato tu la partita")
        return

    if partite[f'{chat_id}'].isStarted:
        update.message.reply_text("Partita già avviata")
        return


    partite[f'{chat_id}'].isStarted = True
    
    ordinePartecipanti = ''

    for p in partite[f'{chat_id}'].getAllPartecipantsIDs():
        ordinePartecipanti += partite[f'{chat_id}'].partecipanti[p].nomeUtente + '\n'


    update.message.reply_text(f"{utente} ha avviato la partita. Da ora cancellerò tutti i messaggi dei partecipanti che:\n - Non contengono una parola sola;\n - Hanno già scritto una parola.\n\nL'ordine dei turni è:\n"+ordinePartecipanti)


# To-Do list:
#   ✔ Fixare errore dei messaggi modificati
#   ✔ Fixare il numeraggio dei partecipanti
#   ✔ Fixare che chiunque può terminare il game
#   ... Aggiungere possibilità di quittare un game
#   Salvare le partite quando il bot si spegne
#   Controllare bene altre cose

def onMessageInGroup(update: Update, context: CallbackContext):
    global partite
    
    chat_id = update.message.chat.id if update.message != None else update.edited_message.chat.id
    utente = (update.message.from_user.username if update.message.from_user.username != None else update.message.from_user.full_name) if update.message != None else (update.edited_message.from_user.username if update.edited_message.from_user.username != None else update.edited_message.from_user.full_name)
    idUtente = update.message.from_user.id if update.message != None else update.edited_message.from_user.id
    messaggio_id = update.message.message_id if update.message != None else update.edited_message
    
    
    if (not f'{chat_id}' in partite) or (not partite[f'{chat_id}'].isStarted):
        return
    
    if update.edited_message != None:
        update.edited_message.reply_text(f'Hey {utente} non puoi modificare un messaggio! La tua parola rimarrà: {storie[f"{chat_id}"].split(" ")[-2]}')
        return
    
    messaggio = update.message.text

    # Se il gruppo non ha una partita creata o la partita non è avviata non proseguire
    
    partecipante = partite[f'{chat_id}'].partecipanti[str(idUtente)]

    if not partecipante.numero == partite[f'{chat_id}'].turno:
        messaggioDaCancellare = update.message.reply_text(f"{utente} non è il tuo turno. Tocca a {partite[f'{chat_id}'].prossimoTurno().nomeUtente}")
        context.bot.delete_message(chat_id,messaggio_id)
        sleep(3)
        context.bot.delete_message(chat_id,messaggioDaCancellare.message_id)
        return

    # To-Do controllo messaggi:
    # - ✔ Non deve contenere spazi
    # - ✔ Non deve contenere i simboli _-+

    if (' ' in messaggio or '_' in messaggio or '-' in messaggio or '+' in messaggio):
        messaggioDaCancellare = update.message.reply_text(f'{utente} devi scrivere una parola sola :P\nil gioco si chiama "ONE WORD stories" per un motivo.')
        context.bot.delete_message(chat_id,messaggio_id)
        sleep(3)
        context.bot.delete_message(chat_id,messaggioDaCancellare.message_id)
        return
    
    if partecipante.hasWritten:
        messaggioDaCancellare = update.message.reply_text(f'{utente} hai già scritto una parola.')
        context.bot.delete_message(chat_id,messaggio_id)
        sleep(3)
        context.bot.delete_message(chat_id,messaggioDaCancellare.message_id)
        return
    
    storie[str(chat_id)] += messaggio + ' '
    partecipante.hasWritten = not partecipante.hasWritten
    partite[f'{chat_id}'].turno += 1

    if all_partecipants_have_written(partite[f'{chat_id}']):
        partite[f'{chat_id}'].turno = 0
        
        for id in partite[f'{chat_id}'].getAllPartecipantsIDs():
            partite[f'{chat_id}'].partecipanti[f'{id}'].hasWritten = False
        
        messaggioDaCancellare = update.message.reply_text(f'Tutti i partecipanti hanno scritto una parola. Ora potete riscrivere')
        sleep(3)
        context.bot.delete_message(chat_id,messaggioDaCancellare.message_id)


def all_partecipants_have_written(partita: Partita) -> bool:

    for idPartecipante in partita.getAllPartecipantsIDs():
        if not partita.partecipanti[f'{idPartecipante}'].hasWritten:
            return False

    return True


def end_game(update: Update, context: CallbackContext):
    
    global partite

    utente = update.message.from_user.username if update.message.from_user.username != None else update.message.from_user.full_name
    idUtente = update.message.from_user.id
    chat_id = update.message.chat.id
    messaggio = update.message.text
    messaggio_id = update.message.message_id
    
    if not f'{chat_id}' in partite:
        update.message.reply_text("Devi prima creare una partita.")
        return

    if not idUtente == partite[f'{chat_id}'].whoCreatedId:
        update.message.reply_text(f"{utente} non hai avviato tu la partita! Puoi usare /quit_ows_game al massimo")
        return

    if (storie[f'{chat_id}'] != ""):
        update.message.reply_text("Termino la partita. Ecco la vostra storia:")
        update.message.reply_text(capwords(storie[f'{chat_id}'],'. '))
    else:
        update.message.reply_text("Termino la partita.")


    # Azzero qualsiasi cosa possibile per cancellare la partita
    partite.pop(f'{chat_id}',None)
    storie.pop(f'{chat_id}',None)
    

def quit_ows_game(update: Update, context: CallbackContext):
    global partite
    
    utente = update.message.from_user.username if update.message.from_user.username != None else update.message.from_user.full_name
    idUtente = update.message.from_user.id
    chat_id = update.message.chat.id
    messaggio = update.message.text
    messaggio_id = update.message.message_id

    if not f'{chat_id}' in partite:
        update.message.reply_text(f'Non è stata creata nessuna partita. Creane una con /crea_partita')
        return

    if not str(idUtente) in partite[f'{chat_id}'].partecipanti:
        update.message.reply_text(f'Non sei in partita!')
        return
    
    partite[f'{chat_id}'].partecipanti.pop(str(idUtente))
    update.message.reply_text(f"Sei uscito dalla partita con successo. I ")

    pass

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

    dp.add_handler(MessageHandler(Filters.chat_type.groups & ~Filters.command,onMessageInGroup,run_async=True))

    dp.add_handler(CommandHandler("end_game",end_game))

    dp.add_handler(CommandHandler("quit_ows_game", quit_ows_game))

    
    # Questo per ricevere una notifica quando il bot è online; utile all'inizio, dopo disattivalo sennò impazzisci per le notifiche
    requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage?chat_id={ID_OWNER}&text=Bot online")
    
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