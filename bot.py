TOKEN = "5375611900:AAEgn-ZWpJPlZOUI6FeSFb8tHfOJsJSV_Ag" # TOKEN DEL BOT
ID_OWNER = "245996916" # ID TELEGRAM PER RICEVERE NOTIFICA (ottienilo con t.me/JsonDumpBot)

# https://docs.python-telegram-bot.org/en/stable/telegram.ext.handler.html

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
)

from string import capwords

import requests # Per mandare la richiesta di invio messaggio quando online
import logging # Per loggare (non si usa "print()" ma logger.info())

# Questa è la configurazione di base del log, io lo lascio così di solito
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

class Partecipante:
    nextNum = 0
    def __init__(self, username) -> None:
        self.numero = Partecipante.nextNum
        Partecipante.nextNum += 1
        self.nomeUtente = username
        self.hasWritten = False
        


class Partita:
    def __init__(self, utente)-> None:
        self.whoCreated: str = utente
        self.partecipanti: Dict[str,Partecipante] = {}
        self.isStarted: bool = False
        self.turno: int = 0

    def getAllPartecipantsIDs(self):
        return list(self.partecipanti.keys())


#        group_id: Partita()
partite: Dict[str,Partita] = {}

#       group_id: storia
storie: Dict[str,str] = {}


def start(update: Update, context: CallbackContext): # /start
    utente = update.message.from_user.username if update.message.from_user.username != None else update.message.from_user.full_name
    idUtente = update.message.from_user.id
    
    logging.info(f'{utente}, {idUtente} - Ha eseguito /start')
    update.message.reply_text(f'Benvenuto nel bot "One Word Story"')

def help(update: Update, context: CallbackContext): # /help
    utente = update.message.from_user.username if update.message.from_user.username != None else update.message.from_user.full_name
    idUtente = update.message.from_user.id
    
    logging.info(f'{utente}, {idUtente} - Ha eseguito /help')
    update.message.reply_text('Aiuto')

def crea_partita(update: Update, context: CallbackContext):
    global partite
    
    utente = update.message.from_user.username if update.message.from_user.username != None else update.message.from_user.full_name
    idUtente = update.message.from_user.id

    chat_id = update.message.chat.id

    if chat_id > 0:
        update.message.reply_text(f'Hey {utente}, non vorrai mica giocare da solo? Usa questo comando in un gruppo')
        return
    
    if not f'{chat_id}' in partite:
        partite[f'{chat_id}'] = Partita(utente)
        storie[f'{chat_id}'] = '' 
        partite[f'{chat_id}'].partecipanti[f'{idUtente}'] = Partecipante(utente)
        update.message.reply_text(f'{utente} ha creato una partita')
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


    partite[f'{chat_id}'].partecipanti[f'{idUtente}'] = Partecipante(utente)
    
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

    partite[f'{chat_id}'].isStarted = True
    
    ordinePartecipanti = ''

    for p in partite[f'{chat_id}'].getAllPartecipantsIDs():
        ordinePartecipanti += partite[f'{chat_id}'].partecipanti[p].nomeUtente + '\n'


    update.message.reply_text(f"{utente} ha avviato la partita. Da ora cancellerò tutti i messaggi dei partecipanti che:\n - Non contengono una parola sola;\n - Hanno già scritto una parola.\n\nL'ordine dei turni è:\n"+ordinePartecipanti)

def onMessageInGroup(update: Update, context: CallbackContext):
    global partite

    utente = update.message.from_user.username if update.message.from_user.username != None else update.message.from_user.full_name
    idUtente = update.message.from_user.id
    chat_id = update.message.chat.id
    messaggio = update.message.text
    messaggio_id = update.message.message_id


    # Se il gruppo non ha una partita creata o la partita non è avviata non proseguire
    if (not f'{chat_id}' in partite) or (not partite[f'{chat_id}'].isStarted):
        return
    
    partecipante = partite[f'{chat_id}'].partecipanti[str(idUtente)]

    if not partecipante.numero == partite[f'{chat_id}'].turno:
        messaggioDaCancellare = update.message.reply_text(f'{utente} non è il tuo turno')
        context.bot.delete_message(chat_id,messaggio_id)
        sleep(3)
        context.bot.delete_message(chat_id,messaggioDaCancellare.message_id)
        return

    # Il messaggio per essere valido:
    # - ✔ Non deve contenere spazi
    # - Non deve contenere i simboli: _-+

    if (' ' in messaggio):
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
        messaggioDaCancellare = update.message.reply_text(f'Tutti i partecipanti hanno scritto una parola. Ora potete riscrivere')
        sleep(3)
        context.bot.delete_message(chat_id,messaggioDaCancellare.message_id)


        partite[f'{chat_id}'].turno = 0

        for id in partite[f'{chat_id}'].getAllPartecipantsIDs():
            partite[f'{chat_id}'].partecipanti[f'{id}'].hasWritten = False
    


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
    
    if not partite[f'{chat_id}'].isStarted:
        update.message.reply_text("Devi prima avviare una partita.")
        return

    update.message.reply_text("Termino la partita. Ecco la vostra storia")
    update.message.reply_text(capwords(storie[f'{chat_id}'],'. '))
    
    # Azzero qualsiasi cosa possibile per cancellare la partita
    partite.pop(f'{chat_id}',None)
    storie.pop(f'{chat_id}',None)
    



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
    dp.add_handler(CommandHandler("help", help))

    dp.add_handler(CommandHandler("crea_partita", crea_partita))
    dp.add_handler(CommandHandler("join_ows_game", join_ows_game))
    dp.add_handler(CommandHandler("avvia_partita", avvia_partita))

    dp.add_handler(MessageHandler(Filters.chat_type.group & ~Filters.command,onMessageInGroup,run_async=True))

    dp.add_handler(CommandHandler("end_game",end_game))

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