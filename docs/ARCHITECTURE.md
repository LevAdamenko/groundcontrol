# GroundControl — architecture

GroundControl helps a passenger whose flight was cancelled or delayed. It reads the passenger's
description of what happened (free text, a boarding-pass text dump, or the airline's email),
works out what Regulation (EC) No 261/2004 ("EU261") gives them, checks every claimed right
against official sources, and drafts two documents: a claim to the airline and, for when the
airline refuses, a complaint to the national enforcement body.

All data in this repo is synthetic. Airlines in the scenarios are fictional. GroundControl
never sends anything to an airline or an authority; it only produces drafts.

## The rule that shapes the design: no proof, no claim

A compensation amount or a right is shown as **verified** only when it carries two things:

1. **A calculation** — the deterministic inputs and the rule that produced it (great-circle
   distance in km, arrival delay in minutes, notice period in days, the article applied).
2. **Evidence** — at least one source on an allow-listed official domain whose text contains
   the anchor phrase for that rule (for example `EUR 600` for the 600 € band).

If either is missing, the item is marked `unverified` and the drafts say so in words
("not verified against an official source"). The letter generator cannot print a verified
amount without both. Tests prove this: removing the evidence or the calculation flips the
status and changes the letter text.

The language model **never** decides the amount. Nemotron extracts facts and writes prose;
the arithmetic and the legal rules are plain Python in `groundcontrol/eu261.py`.

## Pipeline

```
input text ──► 1. extract (Nemotron) ──► FlightFacts
                                            │
                                            ▼
                               2. assess (eu261.py, pure code) ──► Assessment
                                            │                       (entitlements + calculations)
                                            ▼
                               3. verify (Tavily, include_domains) ──► Evidence per entitlement
                                            │
                                            ▼
                               4. draft (template + Nemotron prose) ──► airline claim
                                                                     └► NEB complaint
```

1. **Extract** — `extract.py` sends the input to Nemotron with `response_format: {"type": "json_object"}` (with one retry if JSON parsing fails) and gets back
   `FlightFacts`: flight number, operating carrier, departure/arrival airports (IATA),
   scheduled and actual times, disruption type, stated reason, notice date for cancellations,
   rerouting offered. The response is validated; missing or invalid fields become explicit
   `None` and are listed in `Assessment.missing_facts`, never guessed.
2. **Assess** — `eu261.py` takes `FlightFacts` and returns an `Assessment`: whether EU261
   applies (and why not, if it does not), the distance band, the compensation amount with
   any 50 % reduction, the care and rerouting/refund rights, and a `disputed` flag on
   compensation when the stated reason is one the airline is likely to invoke (extraordinary
   circumstances).
3. **Verify** — `verify.py` queries Tavily with `include_domains` = the allow-list below
   (one search per entitlement, or two for the 300 € reduced case) and checks that a result
   contains the anchor phrase. Results outside the allow-list are dropped even if Tavily
   returns them. If Tavily fails or its key is missing, `assessment.verification_error` is
   set and the run completes with unverified entitlements.
4. **Draft** — `drafts.py` fills a fixed letter structure. Amounts, articles and dates come
   from the `Assessment`; Nemotron only writes the short narrative paragraph. After drafting,
   a guard checks that every euro amount appearing in the model's prose equals the computed
   amount; otherwise the prose is replaced by a neutral template sentence.

### Official source allow-list

| Domain | What it is |
|---|---|
| `eur-lex.europa.eu` | Text of Regulation 261/2004 and CJEU judgments |
| `curia.europa.eu` | CJEU case law (Sturgeon, Wallentin-Hermann, …) |
| `europa.eu` | Your Europe passenger-rights pages, list of national enforcement bodies |
| `transport.ec.europa.eu` | Commission interpretative guidelines |
| `ulc.gov.pl` | Urząd Lotnictwa Cywilnego, Poland's enforcement body |

## EU261 rules implemented in code

Distance is the great-circle distance between the departure airport and the **final
destination** (haversine, Earth radius 6371.0 km), rounded down to whole km.

**Scope (Art. 3(1)).** EU261 applies when
- the flight departs from an airport in the EU261 area (EU member states, plus Iceland,
  Norway and Switzerland), whatever the carrier; or
- the flight departs from outside the area, arrives inside it, and the **operating** carrier
  is an EU261-area carrier.
Otherwise it does not apply, and the assessment says which condition failed. The UK is a third
country: a UK departure is covered only on an EU261-area carrier flying into the area. For other
UK departures the assessment points to the UK's own regulation (UK261), which GroundControl
does not implement.

**Compensation bands (Art. 7(1)).**
| Distance | Amount |
|---|---|
| ≤ 1500 km | 250 € |
| > 1500 km, flight within the EU261 area | 400 € |
| > 1500 km and ≤ 3500 km, other flights | 400 € |
| > 3500 km, other flights | 600 € |

"Within the EU261 area" means both airports are in the area.

**Delay (Art. 6 + CJEU C-402/07 Sturgeon, C-452/13 Germanwings).** Compensation is owed when
the arrival at the final destination is **3 hours (180 min) or more** later than scheduled.
Exactly 180 min qualifies; 179 min does not. For the 600 € band, an arrival delay of at least
180 min and less than 240 min gives 300 € (the Art. 7(2)(c) reduction as applied in
Sturgeon). In the 250 € and 400 € bands, a delay of 180 min or more always gives the full
amount.

**Cancellation (Art. 5(1)(c)).** Compensation is owed unless the passenger was told
- 14 days or more before scheduled departure; or
- 7–13 days before, and offered rerouting that departs no more than 2 h before the original
  departure and arrives less than 4 h after the original arrival; or
- less than 7 days before, and offered rerouting that departs no more than 1 h before and
  arrives less than 2 h after.
If compensation is owed and the passenger took a rerouting, the Art. 7(2) 50 % reduction
applies when the rerouted arrival is no more than 2 h (≤ 1500 km), 3 h (400 € band) or
4 h (600 € band) after the original scheduled arrival.

**Extraordinary circumstances (Art. 5(3), recital 14).** If the stated reason is weather,
air-traffic-control restrictions or strikes by staff outside the airline (ATC, airport),
security risks or political instability, the compensation is computed but marked
`disputed`: the airline may refuse and the passenger should ask for proof. Technical faults
(C-549/07 Wallentin-Hermann) and strikes by the airline's own staff (C-28/20) are **not**
extraordinary, and GroundControl says so with the case reference. Care and
rerouting/refund rights are never removed by extraordinary circumstances.

**Care (Art. 9).** Meals and refreshments, two phone calls or emails, and a hotel plus
transport when an overnight stay is needed. For delays, care starts once the departure delay
reaches 2 h (≤ 1500 km), 3 h (400 € band) or 4 h (600 € band) (Art. 6(1)). For
cancellations, care is always owed (Art. 5(1)(b)).

**Reimbursement or rerouting (Art. 8).** Always for cancellations; for delays once the
departure delay reaches 5 h (Art. 6(1)(iii)).

Denied boarding and downgrading are out of scope for the hackathon.

## National enforcement body

The complaint goes to the body of the country of the departure airport (for flights into the
area, the arrival airport). The demo carries a static table — Poland (ULC), Germany (LBA),
France (DGAC), Spain (AESA), Portugal (ANAC). The complaint draft says that the airline must be
contacted first.

## Code layout

```
groundcontrol/
  config.py          env + LIVE switch; loads ~/.config/hackathon/secrets.env if present
  airports.py        IATA → name, country, lat, lon; EU261-area country set
  carriers.py        fictional carriers with home country (EU261-area or not)
  models.py          dataclasses: FlightFacts, Calculation, Evidence, Entitlement, Assessment
  eu261.py           pure rules above; no I/O
  clients/
    nemotron.py      OpenAI-compatible client for Nebius Token Factory, replay mode
    tavily.py        REST client for api.tavily.com/search, replay mode
  extract.py         step 1
  verify.py          step 3
  drafts.py          step 4
  pipeline.py        run(input_text) -> Result
  demo.py            python -m groundcontrol.demo --offline [--scenario ID]
  web.py             FastAPI web adapter
  static/            web UI (index.html)
fixtures/
  scenarios/         synthetic inputs + expected outcome per scenario
  nemotron/          replayed chat completions, keyed by request hash
  tavily/            replayed search responses, keyed by request hash
tests/
```

## External calls and offline mode

Every external call goes through `clients/`. Each client has two modes:
- `LIVE=0` (default, and always in tests): look up the response in `fixtures/` by a stable
  hash of the request (model or endpoint + normalized payload). A missing fixture raises
  `FixtureMissing` with the hash, so a test never silently goes online.
- `LIVE=1`: real HTTP call. `scripts/record_fixtures.py` runs the scenarios live and writes
  the responses into `fixtures/`, marked `"recorded": true`.

Hand-written fixtures created before the keys exist are marked `"recorded": false`, and the
demo prints which mode and which kind of fixture it used.

Nemotron: `base_url=https://api.tokenfactory.nebius.com/v1`, key `NEBIUS_API_KEY`, model
`NEMOTRON_MODEL` (default `nvidia/nemotron-3-super-120b-a12b`). Tavily: `TAVILY_API_KEY`,
`POST https://api.tavily.com/search`. Keys come only from the environment; they are never
written to fixtures, logs or output.

## Failure modes

- **Offline free text without a fixture**: returns HTTP 409 (`FixtureMissing`).
- **Nemotron / Token Factory failure or bad/missing key**: returns HTTP 502 via `UpstreamError`. Nothing is calculated.
- **Tavily failure or missing key (`TAVILY_API_KEY`)**: the run completes (HTTP 200) with all items `unverified`. `assessment.verification_error` is populated and displayed as a warning in the UI, and drafts say "not verified against an official source".

## Synthetic scenarios

| ID | Situation | Expected outcome |
|---|---|---|
| `cancel-short-notice` | WAW → LIS on Vistula Air (fictional, PL), cancelled, told 5 days before, no rerouting taken | EU261 applies, 400 € (intra-area > 1500 km), care + refund/rerouting |
| `delay-3h40` | WAW → CDG on Vistula Air, arrives 3 h 40 min late, technical fault | 250 €, not extraordinary (C-549/07) |
| `delay-weather` | WAW → JFK on Vistula Air, arrives 5 h late, thunderstorm | 600 € marked `disputed`, care owed, refund option (≥ 5 h) |
| `longhaul-3h30` | WAW → JFK on Vistula Air, arrives 3 h 30 min late, crew shortage | 300 € (50 % reduction, 3–4 h band) |
| `outside-scope` | DXB → WAW on Gulf Horizon (fictional, non-EU), arrives 6 h late | EU261 does not apply: departs outside the area on a non-EU carrier |

## How this differs from PaperTrail

PaperTrail reads letters from government offices and tracks deadlines for one case over time.
GroundControl is a one-shot calculator-and-drafter for a single travel disruption: the core is
a deterministic rules engine with distance and time arithmetic, and the output is a pair of
legal drafts. They share no code.
