# WoW Forever → Telegram

Bot che ogni 20 minuti raccoglie le news su **World of Warcraft: Forever** e le pubblica su un canale Telegram.
Gira gratis su GitHub Actions, senza server.

**Fonte:** le news di [Wowhead](https://www.wowhead.com/news) che parlano di Forever, in lingua originale (inglese).
Ogni messaggio ha l'immagine dell'articolo (se c'è), il titolo in grassetto, la data con gli hashtag, il testo in una citazione espandibile (elenchi compresi) e il pulsante "Leggi su Wowhead".
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
- **Frequenza**: modifica la riga `cron` in `.github/workflows/bot.yml`.
- **Prova in locale**: `pip install -r requirements.txt && DRY_RUN=1 python bot.py`. Stampa i messaggi invece di inviarli.

> GitHub sospende i workflow programmati se il repo non riceve attività per 60 giorni.
> Qui non succede, perché il bot salva un commit ogni volta che trova news nuove.
