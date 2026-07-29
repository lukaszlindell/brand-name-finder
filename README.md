# Brand Name Finder

Ett enkelt verktyg som skapar varumärkesnamn, kontrollerar om `.com` och `.se`
verkar lediga, rangordnar kandidaterna och sparar resultatet i tre format:

- `results/RESULTS.md` – kan läsas direkt på GitHub
- `results/results.html` – en tydlig webbsida
- `results/results.csv` – för Google Sheets eller andra kalkylprogram

Du behöver inte installera Python eller ha Excel. Allt kan köras med knappar på
GitHub.

## Kör verktyget – klick för klick

1. Öppna repot på GitHub.
2. Klicka på fliken **Actions**.
3. Klicka på **Hitta lediga varumärkesnamn** i vänsterspalten.
4. Klicka på knappen **Run workflow**.
5. Välj hur många namn som ska kontrolleras. `200` är en bra start.
6. Ändra **seed** om du vill få en ny blandning av namn.
7. Skriv eventuella egna namn i **custom_names**, separerade med kommatecken.
8. Klicka på den gröna knappen **Run workflow**.
9. Vänta tills körningen får en grön bock och öppna den.
10. Läs topplistan direkt i körningens sammanfattning.

Resultatet sparas dessutom i mappen [`results`](results/) i repot. Längst ned på
körningens sida finns också den nedladdningsbara filen **brand-name-results** med
CSV, Markdown och HTML.

## Så fungerar rangordningen

Namn får högre poäng när:

- `.com` verkar ledig
- `.se` verkar ledig
- längden är ungefär 6–8 bokstäver
- bokstavsmönstret är relativt lätt att uttala på svenska och engelska

`.com` väger klart tyngst. Ett namn med registrerad `.com` hamnar därför långt
ned även om `.se` är ledig.

## Viktigt innan du registrerar

En ledighetskontroll är en ögonblicksbild, inte en reservation eller garanti.
Domänen kan registreras av någon annan direkt efter körningen, vara reserverad
eller ge ett oklart svar. Kontrollera därför alltid toppnamnen hos den registrar
du tänker köpa från.

Domänkontrollen säger inte heller att namnet är tillåtet som bolagsnamn eller
varumärke. Resultatfilerna innehåller länkar för manuell slutkontroll hos:

- [Bolagsverket – Sök företagsinformation](https://foretagsinfo.bolagsverket.se/sok-foretagsinformation-web/foretag)
- [TMview – europeisk varumärkessökning](https://www.tmdn.org/tmview/)

Sök även liknande stavningar och namn med samma uttal. Bolagsverket gör en egen
förväxlingsbedömning när bolagsnamnet anmäls.

## Tekniskt

- `.com` kontrolleras via Verisigns RDAP-tjänst.
- `.se` kontrolleras via Internetstiftelsens tjänst `Free`.
- GitHub Actions körs endast manuellt genom `workflow_dispatch`.
- Resultat committas automatiskt tillbaka till repot och sparas som en artifact
  i 30 dagar.

För en snabb lokal testkörning utan nätverksuppslag:

```bash
python -m pip install -r requirements.txt
python brand_name_finder.py --max-names 10 --dry-run
```
