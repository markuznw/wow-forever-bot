# WoW Forever → Telegram

Bot che ogni 20 minuti raccoglie le news su **World of Warcraft: Forever** e le pubblica su un canale Telegram.
Gira gratis su GitHub Actions, senza server.

**Fonti:** Wowhead, Warcraft Tavern, Blizzard News e Google News (in inglese e in italiano).
Tiene solo le notizie che parlano di "Forever" e non ripubblica le notizie che ha già inviato.
Se una fonte non risponde, la salta e continua con le altre.

## Configurazione (una volta sola)

1. **Crea il bot**: su Telegram scrivi a [@BotFather](https://t.me/BotFather), usa `/newbot` e copia il token.
2. **Aggiungilo al canale**: apri il canale → Amministratori → aggiungi il bot con il permesso "Pubblica messaggi".
3. **Inserisci i secret** nel repo, da *Settings → Secrets and variables → Actions → New repository secret*:
   - `TELEGRAM_BOT_TOKEN` = il token del bot
   - `TELEGRAM_CHANNEL` = `@nomedelcanale`, oppure il link di un argomento di un gruppo (es. `https://t.me/c/1234567890/39`): il bot pubblica in quell'argomento
4. **Avvialo**: tab *Actions* → "WoW Forever news → Telegram" → *Run workflow*.

Al primo avvio pubblica solo le 3 news più recenti. Da lì in poi pubblica solo quelle nuove, fino a 10 per giro.

## Personalizzare

- **Fonti**: modifica la lista `FEEDS` in `bot.py`.
- **Frequenza**: modifica la riga `cron` in `.github/workflows/bot.yml`.
- **Prova in locale**: `pip install -r requirements.txt && DRY_RUN=1 python bot.py`. Stampa i messaggi invece di inviarli.

> GitHub sospende i workflow programmati se il repo non riceve attività per 60 giorni.
> Qui non succede, perché il bot salva un commit ogni volta che trova news nuove.
