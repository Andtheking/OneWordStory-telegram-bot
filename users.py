def saveUser(id, username, language):
    if userExists(id):
        return
        
    with open("utenti.txt","a") as f:
        f.write(f"{id} - {username} - {language}\n")

def userExists(userId: str|int):
    with open("utenti.txt","r+") as f:
        for utente in f:
            id = utente.split(" - ")[0]

            if id == str(userId):
                return True
    
    return False

def loadUser():
    a : str
    with open("utenti.txt","r") as f:
        a = f.readlines()

def getUserLang(id) -> str:
    all_users: str    
    with open("utenti.txt","r") as f:
        all_users = f.readlines()

    for user in all_users:
        if user.split(" - ")[0] == id:
            return user.split(" - ")[2]
    
    return "it"

def editUserLang(id, lang):
    utenti = open("utenti.txt","r").readlines()

    for i,utente in enumerate(utenti):
        infoUtente = utente.split(' - ')
        if infoUtente[0] == id:
            utenti[i] = f"{infoUtente[0]} - {infoUtente[1]} - {lang}\n"

    with open("utenti.txt","w") as f:
        for utente in utenti:
            f.write(utente)
    

if __name__ == '__main__':
    saveUser("1234","@Andtheking","it")
    saveUser("43535","@Frankekko","it")
    saveUser("76574","@Jhon","it")
    saveUser("1231265","@Luca","it")
    saveUser("78564","@Sabri","it")


    print(getUserLang("1234"))

    editUserLang("76574", "en")

    print(getUserLang("1234"))