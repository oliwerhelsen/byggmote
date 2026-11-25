# Byggmöte på en dator: säkerhetsnotis för IT

[English](security.en.md) · Kontakt och rapportering: [SECURITY.md](../SECURITY.md)

Skriven från koden som den är. Det koden inte gör står inte här som ett löfte; luckor står under **Luckor**. Gäller
`app/` (Electron) och `engine/` (Python), version 0.1.0, som installerare (Windows `.exe`, Linux `.deb` och AppImage, Mac
`.dmg`; `README.md`, Installing). Installerarna är ännu inte signerade (se Luckor).

Ljudet och hela transkriptet lämnar aldrig datorn. Tal, talare och protokoll görs lokalt. Det enda som går till Stommen
är inloggningen och, när personen trycker på Skicka och godkänner listan, protokollets punkter.

## Vad som lagras och var

| Vad | Var | Innehåll |
| --- | --- | --- |
| Appens inställningar | Appens egen mapp (`userData`, för en installerad app `Byggmote`): macOS `~/Library/Application Support/Byggmote`, Windows `%APPDATA%\Byggmote`, Linux `~/.config/Byggmote` | `settings.json`: namn, mikrofon, Känn igen röster av/på, starta vid inloggning, om första start är gjord. Ingen hemlighet. |
| Stommen-anslutningen | Samma mapp, `stommen.json` (rättighet 0600) | Stommens adress, personens namn och organisationens namn, tid för senaste hämtning och sessionstoken. Token är krypterad med operativsystemets nyckelring (macOS Nyckelring, Windows DPAPI, Linux libsecret). Finns ingen nyckelring, eller är den Linux-reservens fasta nyckel, sparas ingen token: den lever tills appen stängs. Lösenordet sparas aldrig. |
| Kunskapsbasen | `Dokument/Byggmöte` (eller mappen personen väljer; pekaren ligger i `~/.config/byggmote/byggmote.json`, Linux `$XDG_CONFIG_HOME/byggmote`) | `areas.json` (projekt), `people.json` (namn, e-post, kopplingar till Stommen), `learning.json`, och en mapp per möte: `meeting.json` (talare, transkript, och röstavtryck när Känn igen röster är på), `transcript.txt`, `audio.m4a`, `protocol.json`, `protocol.md`. Okrypterat, med filsystemets rättigheter. Kan ligga i en delad mapp (OneDrive, Teams) om personen väljer det. |
| Inspelning under pågående möte | Tillfällig mapp, `byggmote-recordings/<id>.webm` | Skrivs en sekund i taget, tas bort när mötet har sin egen kopia. |
| Modeller | Hugging Faces cache: `~/.cache/huggingface/hub` (eller `HF_HOME` / `HF_HUB_CACHE`) | Se `NOTICE.md`: fem modeller, 30 MB till 6 GB styck, hämtade på en fast commit. |
| Fönstrets egna filer | `userData` | Chromiums vanliga cache och lagring. Fönstret läser bara appens lokala filer. |

## Vad som skickas, och vart

| Till | När | Vad |
| --- | --- | --- |
| Stommen, `https://app.stommen.io` (personen kan ange en annan adress; bara https, eller http för den egna datorn) | Inloggning, "Hämta från Stommen", appstart när personen är inloggad, utloggning | `POST /api/auth/sign-in/email` (e-post, lösenord), `GET /api/mobile/v1/me`, `/projects`, `/projects/<id>/roles`, `POST /api/auth/sign-out`. Rubrikerna `X-App: byggmote` och `X-App-Version`. Ingen omdirigering följs. |
| Stommen, `POST /api/mobile/v1/projects/<id>/minutes` | Bara när personen trycker Skicka och godkänner listan, och inga kontroller återstår | Möteserie och möte (nummer, datum, längd), deltagare (namn, roll), rubriker, protokolltexten, och per punkt: nummer, rubrik, typ, text, roll, datum, öppen, hur många sekunder in i inspelningen den sades, **raden som sades där** och **vem som sa den**, om den skrevs av modellen, ändrades eller lades till av en person, bekräftade belopp. |
| `huggingface.co` (och Hugging Faces egna nedladdningsadresser, som de byter vid behov) | Bara när modeller hämtas: "Modeller" i första start och Inställningar, eller när ett möte körs och en tal- eller talarmodell saknas. Protokollmodellen hämtas aldrig av en körning. | Förfrågan om en fast commit av ett repo, och filerna. Inget om personen eller mötet. Använder operativsystemets certifikatlager, så en TLS-inspektion i företaget fungerar. |
| `otel.pyannote.ai` | **Bara på Mac, när talarmodellen körs, om inget stänger det** (se Luckor) | Bibliotekets version, ett slumpat sessions-id, ljudets längd i sekunder, antal talare. Inte ljud, inte text. |
| Systemets webbläsare | Personen klickar en https-länk i fönstret | Ingenting från appen. |

Inget annat. Fönstret kan inte kalla ut (`Content-Security-Policy: connect-src 'self'`), laddar inga teckensnitt eller
skript utifrån, och appen har ingen uppdateringsfunktion, ingen kraschrapportering och ingen analys (sökt i koden).
Språkmodellens server lyssnar bara på `127.0.0.1`, med en nyckel per körning, `--offline`, och förbigår datorns proxy.

**Telemetri.** I Byggmötes egen kod finns ingen. Undantaget är pyannote-audio 4.0.7 på Mac: **den är påslagen som
standard i dag**, Byggmöte stänger inte av den, och den slås av med `PYANNOTE_METRICS_ENABLED=false` (kontrollerat: med den satt slås inget upp, utan den slås
`otel.pyannote.ai` upp). På Windows och Linux används inte pyannote. Chromium i Electron har vi inte fångat trafiken
från; se Luckor.

## Processer appen startar

| Process | Hur | Anmärkning |
| --- | --- | --- |
| Motorn `byggmote` (Python) | Ett kommando per uppgift. En installerad app startar sin egen Python (`resources/engine/python`); annars `BYGGMOTE_ENGINE` eller `engine/.venv`; ärver appens miljö; stängs när appen stängs | Gör all inspelningsbearbetning, kunskapsbasen och modellhämtningen. |
| `ffmpeg`, `ffprobe` | Av motorn. Den installerade appen lägger sin egen kopia (`resources/engine/bin`) först på sökvägen; en utvecklingskörning använder datorns | I installeraren fastlåsta byggen med kontrollsumma: BtbN (LGPL 2.1) på Windows och Linux, Martin Riedl (GPL 3.0) på Mac. |
| `llama-server` (llama.cpp) | Av motorn, en gång per protokoll; `BYGGMOTE_LLAMA_SERVER`, den installerade appens egen (`resources/engine/bin/llama`), annars `engine/bin`, annars `PATH` | `127.0.0.1`, slumpad port, `--offline --no-webui`. Med i installerarna för Windows och Linux, build b12590 med kontrollsumma. Mac-installeraren har ingen: på Mac används `mlx-lm` i Python. |
| `taskkill` | Windows, för att stoppa motorn | |
| `id -F` | macOS, för personens fulla namn | |

Appen ber om mikrofonen och inget annat som en sida kan be om. Fönstret körs i sandlåda, utan Node.

## Modeller och bibliotek

Namn, version, commit och licens: [NOTICE.md](../NOTICE.md). `python3 scripts/check-notice.py` misslyckas när listan
inte stämmer med koden, och CI kör den. CI gör också en programvarulista (SBOM, CycloneDX) för varje release:
`scripts/sbom.py`, bifogad releasen som `byggmote-sbom.cdx.json` när releasen publiceras (installerarna byggs av
`release.yml` som ett utkast till release). Den har alla låsta paket och modellerna, men inte de inbyggda `ffmpeg`,
`llama-server` och Python: de står med version och licens i NOTICE.md och i `app/scripts/bundle-engine.sh`.

## Uppdatering

Appen uppdaterar sig inte. IT installerar en ny version (tyst: Windows `/S /allusers`, Linux `apt install`, Mac kopiera från
diskavbilden; kommandona står i `README.md`). En avinstallation tar bara bort programmet, inte möten, inställningar eller modeller. Modellerna byts bara när en ny version ändrar commiten i
`models.py`, och hämtas då vid nästa användning.

## Stäng av Stommen

- Logga inte in. Utan inloggning ringer appen aldrig till Stommen, och steget går att hoppa över i första start.
- Inloggad: **Logga ut** i Stommen-vyn avslutar sessionen hos Stommen och tar bort token från datorn.
- Hårt: blockera `app.stommen.io` (och en annan adress personen kan ha angett) i brandväggen. Appen fungerar då utan
  Stommen.
- Det finns ingen inställning som stänger anslutningen permanent för alla användare (se Luckor).

## Blockera modellhämtningen, eller använd en egen kopia

1. Blockera `huggingface.co` och dess nedladdningsadresser, eller sätt `HF_HUB_OFFLINE=1` i appens miljö. Då hämtas inget; en modell som saknas ger ett fel.
2. Lägg modellerna där motorn letar: Hugging Face-cachen, i dess mappformat `models--<ägare>--<namn>/snapshots/<commit>/` med filerna för den commit som står i `NOTICE.md`. Flytta cachen med `HF_HOME` eller `HF_HUB_CACHE`, eller peka på en egen spegel med `HF_ENDPOINT`.
3. En modell räknas som hämtad när dess filer finns i cachen på just den committen. Talarmodellen på Mac kan också läggas i `BYGGMOTE_MODELS/pyannote-community-1` (med `config.yaml`).

Miljövariablerna gäller motorn, som ärver appens miljö. En app som startas från Finder eller Start ser inte ett
skals variabler: sätt dem i systemet (MDM, `launchctl setenv`, systemvariabel).

## Luckor

Funna när detta skrevs. Inget av det här lovas som rättat.

1. **pyannote-telemetri på Mac är på.** Byggmöte stänger inte av den. Åtgärd tills vidare: `PYANNOTE_METRICS_ENABLED=false` i miljön, eller blockera `otel.pyannote.ai`.
2. **Ingen avstängning av Stommen för alla.** Inloggningsformuläret finns alltid; ingen policy eller konfigurationsfil stänger det.
3. **Ingen nätverksfångst av hela appen.** Kontrollerat: koden, och uppslagningen av `otel.pyannote.ai` när motorns bibliotek körs. Inte kontrollerat: Chromiums och Electrons egen trafik, eller en körning av hela appen med fångst.
4. **Okrypterad kunskapsbas.** Ljud, transkript, namn och röstavtryck ligger som vanliga filer. Skyddet är datorns diskkryptering och filrättigheter.
5. **Utvecklingskörningar** (inte installerade) använder datorns `ffmpeg` och `llama-server`, så deras version och licens beror på datorn.
6. **Installerarna är inte signerade.** Mac: bara ad hoc (inte notariserad), så Gatekeeper varnar. Windows: ingen kodsignering, så SmartScreen varnar och AppLocker kan blockera. Linux: inga signaturer. Signering görs bara när certifikaten finns som hemligheter i repot (`release.yml`); så ser det ut i dag enligt `README.md`.
7. **Hugging Faces nedladdningsadresser** (CDN) är inte fastlåsta av oss och kan byta; listan över dem är inte kontrollerad.
