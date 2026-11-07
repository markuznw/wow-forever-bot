# WoW Forever → Telegram

Bot che ogni 20 minuti raccoglie le news su **World of Warcraft: Forever** e le pubblica su un canale Telegram.
Gira gratis su GitHub Actions, senza server.

**Fonte:** le news di [Wowhead](https://www.wowhead.com/news) che parlano di Forever, in lingua originale (inglese).
Ogni messaggio ha l'immagine dell'articolo (se c'è), il titolo in grassetto, la data con gli hashtag, il testo in una citazione espandibile (elenchi compresi) e il pulsante "Leggi su Wowhead".

**Blue post:** i messaggi dello staff Blizzard sulla sezione WoW: Forever del forum ufficiale vengono pubblicati come **immagine in stile "blue post"** (testo azzurro, autore e ruolo). I post lunghi diventano un album di più immagini (massimo 10), tagliate tra una riga e l'altra, seguito da un messaggio con il riassunto a punti e i pulsanti Wowhead/Forum. I post corti sono un'immagine con il riassunto nella didascalia. Per disattivarli crea la variabile `BLUE_POSTS` con valore `off`.
Se nel repo (nella cartella principale o in `assets/`) c'è un'immagine con "logo" nel nome (png, webp, avif o jpg), viene mostrata nell'intestazione dell'immagine; altrimenti viene usato il logo di WoW: Forever scaricato online (indirizzo modificabile con la variabile `LOGO_URL`).

**Notifiche:** i messaggi vengono inviati silenziosi (senza suono/notifica). Per riattivare le notifiche crea la variabile `SILENT` con valore `off`.
Tiene solo le notizie che parlano di "Forever" e non ripubblica le notizie che ha già inviato.

## Configurazione (una volta sola)

1. **Crea il bot**: su Telegram scrivi a [@BotFather](https://t.me/BotFather), usa `/newbot` e copia il token.
2. **Aggiungilo al canale**: apri il canale → Amministratori → aggiungi il bot con il permesso "Pubblica messaggi".
3. **Inserisci i secret** nel repo, da *Settings → Secrets and variables → Actions → New repository secret*:
   - `TELEGRAM_BOT_TOKEN` = il token del bot
   - `TELEGRAM_CHANNEL` = `@nomedelcanale`, oppure il link di un argomento di un gruppo (es. `https://t.me/c/1234567890/39`): il bot pubblica in quell'argomento
4. **Avvialo**: tab *Actions* → "WoW Forever news → Telegram" → *Run workflow*.

Se il bot non riesce ad accedere al gruppo o al canale, l'esecuzione fallisce (in rosso) e il log spiega il motivo.

Al primo avvio pubblica le 10 news più recenti. Da lì in poi pubblica solo quelle nuove, fino a 10 per giro.

## Personalizzare

- **Fonti**: modifica la lista `FEEDS` in `bot.py`.
- **Traduzione automatica (opzionale, spenta di default)**: crea la variabile `TRANSLATE_TO` con valore `it` in *Settings → Secrets and variables → Actions → Variables*. Usa Google Translate gratuito; se non risponde il bot pubblica il testo originale. Per spegnerla elimina la variabile o mettila a `off`.
- **Frequenza**: modifica la riga `cron` in `.github/workflows/bot.yml`. GitHub non garantisce l'orario esatto: le esecuzioni programmate possono partire in ritardo o, su repo nuovi, iniziare dopo un po'.
- **Prova in locale**: `pip install -r requirements.txt && DRY_RUN=1 python bot.py`. Stampa i messaggi invece di inviarli.

> GitHub sospende i workflow programmati se il repo non riceve attività per 60 giorni.
> Qui non succede, perché il bot salva un commit ogni volta che trova news nuove.
