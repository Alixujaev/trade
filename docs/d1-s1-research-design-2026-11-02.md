# D1 va S1: matematik spetsifikatsiya va research protocol draft (2026-11-02)

> **Holat: DRAFT — PROPOSED, NOT ADOPTED, NOT AUTHORIZED TO RUN.**
> Bu hujjat dizayn hujjati. Backtest, optimizatsiya, data acquisition, broker yoki live execution qilinmagan.
> Hech qanday bozor narxi, bar qiymati yoki strategiya natijasi o'qilmagan. Hujjatdagi har bir raqamli parametr
> **PROPOSED — REQUIRES APPROVAL** yoki **OPEN DECISION** deb belgilangan. Yakuniy tasdiq protocol owner'ga tegishli.

**Belgilar:**
- **FACT**: repo'dagi fayldan to'g'ridan-to'g'ri o'qilgan (manba ko'rsatilgan).
- **INF**: xulosa (inference).
- **PROPOSED**: taklif; dalil bilan qo'llab-quvvatlanadigan qabul qilingan siyosat yo'q, tasdiq talab qilinadi.
- **OPEN**: foydalanuvchi qarori kerak; baseline undan bog'liq.
- **BLOCKED**: kerakli data yoki ruxsat yo'q.

---

## 0. Repository audit (Phase 1)

### 0.1 Holat

| Item | Qiymat |
|---|---|
| Ishchi papka | `C:/Users/Admin/Desktop/own/trade` |
| Branch | `feature/day-trading-research` |
| HEAD | `07cb04e43fa079117d3276722796047a247db8f8` ("docs: add V2-MOM unified evidence summary") |
| Working tree (boshlanishda) | toza (`git status --short` bo'sh) |

### 0.2 D1/S1 hujjatlari

- **FACT: repo'da D1 (`D1-VWAP-RECLAIM`) yoki S1 (`S1-DAILY-TREND-PULLBACK`) bo'yicha hech qanday draft, kod yoki
  artefakt yo'q.** `D1-VWAP`, `S1-DAILY`, `vwap reclaim`, `trend pullback` bo'yicha qidiruv faqat oldingi
  tadqiqotlarni topdi (quyida).
- Nomlar to'qnashuvi: `artifacts/day25b/run/d1.json` bu V2-MOM robustness diagnostikasi D1 (DAY-25B), D1 strategiyasi
  bilan aloqasi yo'q. Uni ochish kerak emas.
- **ChatGPT draftlarining o'zi repo'da yo'q.** Shuning uchun bu hujjat ularni qayta ishlamaydi; vazifa matnidagi
  qisqa tavsif (ID, timeframe, long-only) asosida noldan aniqlaydi. Draftdagi qoidalar bu hujjatdan farq qilsa,
  farqlar alohida solishtirilishi kerak (OPEN-G1).

### 0.3 D1 uchun eng muhim oldingi dalil: VWAP oilasi allaqachon sinalgan

- **FACT:** DAY-01 strategiyasi "VWAP reclaim/hold + RSI>50 + RVOL≥2 + 5m trigger + 15m context", DAY-02 execution
  "T+1 open, SIGNAL_LOW stop, 2R, STOP_FIRST, 15:55 exit" (`artifacts/day13/research-synthesis.md:20-21`).
- **FACT:** 25 symbol, 2026-07-02 → 2026-09-25 (60 sessiya) oynasida 40 ta variant sinalgan; hech biri 5 yoki 10 bps
  da manfiy bo'lmagan natija bermagan (`research-synthesis.md:95`). DAY-15H SIP re-baseline: **research gate FAIL**
  (`artifacts/day15/day15h-alpaca-rebaseline.md:3,11`).
- **FACT:** protocol v1.1 §(line 311): "Derived hypotheses prompted by any v1.1 result ... need a new protocol version
  and **new, later data**, and cannot be confirmed on the v1.1 OOS" (`artifacts/day15/protocol-v1.1.md:311`).
- **Oqibat (INF):** D1 shu oilaning qayta spetsifikatsiyasi. Shu sababli:
  1. 2026-06-03 → 2026-09-28 dagi 5m SIP snapshot (`data/oos_cache/protocol_v1.1/research/...`) va yfinance 5m cache
     **D1 ni baholash uchun yaroqsiz** (ifloslangan: shu oynada 40 variant ko'rilgan).
  2. D1 ni **tasdiqlovchi (confirmatory)** sinov faqat yangi, keyinroq keladigan data'da bo'lishi mumkin (forward).
     Tarixiy, ilgari intraday ko'rilmagan data (masalan 2019–2022) faqat **development/validation** uchun ishlatilishi
     mumkin (OPEN-D1, §5.1).
  3. DAY-05..12B diagnostikalaridan olingan har qanday "saboq" (tor stop, bir sessiyada ko'p kirish, vaqt oynasi)
     D1 dizayniga kirsa, uning provenance'i **MIXED/DERIVED** deb belgilanadi. Bu hujjat har bir shunday joyni belgilaydi.

### 0.4 Data capability: dalil bilan tekshiruv

| Da'vo | Tekshiruv natijasi | Dalil |
|---|---|---|
| Alpaca SIP 5Min | **VERIFIED** (1 probe, HTTP 200, `feed=sip`) | `artifacts/day15/day15e-alpaca-access.md` |
| Alpaca SIP 15Min | **VERIFIED** | `artifacts/day15/day15g-alpaca-15m-access.md` |
| Alpaca SIP 1Day | **VERIFIED** (8 probe, 26/26 symbol, eng erta 2016-01-04) | `artifacts/day17/day17-data-blockers.md` §2, §4 |
| 1Min | **NOT VERIFIED**, kod yo'q; bu bosqich uchun kerak emas | `acquisition/v1_1/contract.py:28` (`5m`, `15m` gina) |
| `data/alpaca_provider.py` | **IEX** (`feed=DataFeed.IEX`) — SIP emas; ishlatilmaydi | `data/alpaca_provider.py:8-12,124` |
| Intraday SIP klient | `acquisition/v1_1/alpaca_client.py` (`feed=sip`, `adjustment=raw`, `end` inclusive) | kod |
| Saqlanadigan intraday ustunlar | OHLCV + `trade_count` + `provider_vwap` (Alpaca `vw`) | `acquisition/v1_1/contract.py:34` |
| Daily SIP klient | `acquisition/v2/bars_client.py` (`timeframe=1Day`, `feed=sip`, `asof`) | `acquisition/v2/contract.py:129-130` |
| Stage R snapshot | mavjud; manifest SHA-256 `aefef19d…6bd` **qayta hisoblandi va mos keldi** (2026-11-02) | `artifacts/day18/day18-stage-r-report.md`; `sha256sum` |
| Stage R yaroqliligi | `USABLE_FOR_RESEARCH, 0 blockers` (protocol v2.0.4, owner sign-off 2026-10-08) | `artifacts/day18l/day18l-protocol-owner-signoff.md` |
| Stage H snapshot | mavjud; **bu hujjatda ochilmadi va ishlatilmaydi** | `acquisition/v2/contract.py:64-72` (faqat konstantalar o'qildi) |
| SPY intraday | **YO'Q** (v1.1 snapshot faqat 25 symbol) | `artifacts/orb/diagnostics_v2/sip_availability.md` §1 |
| QQQ (har qanday timeframe) | **YO'Q** | qidiruv; v2 snapshot = 25 + SPY |
| Earnings kalendari | faqat ORB uchun, qo'lda, **2026-07-02 → 2026-09-25**, 25 symbol; source-verified emas | `config/earnings_calendar.csv`, `data/earnings.py` |
| Corporate actions | Stage R ichida (2016–2022): 483 cash dividend, 6 forward split | `day18-stage-r-report.md` §2 |

### 0.5 Himoyalangan hududlar va vaqt cheklovlari (FACT)

- `fwd-gate2`: 42 sessiya, **2026-10-12 → 2026-12-09**; baholash **2026-12-09 16:15 ET** dan oldin emas
  (`acquisition/v2/contract.py:120`; `docs/strategy-evidence-inventory-2026-10-17.md` §6).
- Forward oyna: 2026-10-08 → 2027-01-07 (`acquisition/v2/contract.py:112`).
- Sealed `V2-MOM-P001`: ledger 2026-12-09 16:15 ET gacha shifrlangan; muddatidan oldin ochish `fwd-gate2` ni
  `FORWARD42-INVALID` qiladi (`artifacts/day27/protocol-v2.3-amendment.md:13,26`).
- DAY-22 §3.2: forward oynada "No forward market data may be acquired into the research cache"; "observations ... during
  the blind period shall not be used to propose ... new strategy variants"
  (`artifacts/day22/day22-protocol-owner-signoff-and-forward-oos-lockdown.md:138-157`).
- **Bu hujjat uchun oqibat:** D1/S1 uchun **2026-10-08 yoki undan keyingi sanadagi hech qanday data** `fwd-gate2`
  baholanmaguncha (kamida 2026-12-09 16:15 ET) olinmaydi va ko'rilmaydi. Bu D1/S1 dizayni forward oynadagi bozor
  kuzatuvlaridan foydalanmaydi (muallif hech qanday narx ko'rmadi). 2026-12-09 dan keyin ham ruxsat OPEN-G2.
- `paper_state/` (sealed, runs, data) ochilmadi.
- Evidence inventory tavsiyasi: yangi tadqiqot va eksperimentlarni `fwd-gate2` baholangunga qadar to'xtatish
  (`docs/strategy-evidence-inventory-2026-10-17.md` §10). Bu hujjat faqat dizayn; u tavsiyaga zid emas, lekin
  har qanday run/acquisition shu tavsiyaga bo'ysunadi.

### 0.6 Mavjud, qayta ishlatilishi mumkin bo'lgan kod (faqat o'qildi)

| Modul | Nima qiladi | D1/S1 uchun |
|---|---|---|
| `indicators/vwap.py` | session VWAP, TP=(H+L+C)/3, 09:30 ET reset, RTH-only, zero-volume → NaN | D1 B-variant VWAP (§1.1) |
| `data/session.py` | RTH/premarket, session date, ET | D1 session chegaralari |
| `indicators/atr.py`, `ema.py`, `rvol.py` | ATR, EMA, RVOL | D1/S1 (formulalar §1, §2 ga qarab tekshirilishi kerak) |
| `backtest/execution.py` | `same_bar_rule == "STOP_FIRST"` | collision qoidasi (§1.5) |
| `strategy/position_sizing.py` | `shares = risk_pct·equity/(entry−stop)`, **fractional** | **mos emas**: 0.5% va `floor` kerak (§3) |
| `screening/eligibility.py` | fail-closed Sharia registry | §4 |
| `data/earnings.py` | fail-closed earnings kalendari | S1 earnings (§2.6) |

Kod o'zgartirilmadi. Implementatsiya keyingi, alohida tasdiqlangan bosqichda.

---

## 1. D1 — `D1-VWAP-RECLAIM` (Phase 2)

### 1.0 Belgilar va vaqt semantikasi

- Sessiya `d`, faqat RTH. Normal kun: 09:30–16:00 ET, `N_d = 78` ta 5m bar; qisqa kun (13:00 ET): `N_d = 42`.
- 5m bar `i ∈ {0..N_d−1}`: interval `[t_i, t_i + 5m)`, `t_i = 09:30 + 5i` daqiqa ET. Alpaca label = bar boshi
  (FACT, DAY-15E §3 #8).
- Bar `i` ning `O_i, H_i, L_i, C_i, V_i, vw_i` qiymatlari **faqat `t_i + 5m` dan keyin** ma'lum.
- **Asosiy qoida (no-lookahead):** bar `r` dagi qaror faqat `{bar_j : j ≤ r}` ga bog'liq va eng erta
  bar `r+1` ning ochilishida bajariladi. Bar `r` ning hech qaysi narxida fill bo'lmaydi.
- `tick = 0.01` USD.
- `CloseTime_d` = 16:00 ET yoki 13:00 ET; `τ_r = t_r + 5m` (bar `r` tugagan vaqt).

### 1.1 VWAP

**Reset:** har sessiyada 09:30 ET da (bar 0). **Faqat RTH.** Premarket va post-market kirmaydi.

**Baseline formula (A, PROPOSED):** Alpaca bar `vw` (bar ichidagi savdolarning hajm bo'yicha o'rtacha narxi) asosida:

```
VWAP_r = Σ_{i=0..r} vw_i · V_i  /  Σ_{i=0..r} V_i
```

- Agar `vw_i` va `V_i` bir xil savdolar to'plamidan hisoblansa, `Σ vw_i·V_i = Σ p·q` (sessiyadagi barcha savdolar
  bo'yicha), ya'ni A formula **trade-level session VWAP ga teng** bo'ladi. Bu **NOT VERIFIED**: Alpaca `vw` va `v`
  uchun bir xil trade-condition filtrini ishlatadimi, hujjatlashtirilmagan. Tekshiruv (data qo'lga kelgach, natija
  emas, data-quality): har bir bar uchun `L_i ≤ vw_i ≤ H_i`.
- **Variant B (fallback):** `TP_i = (H_i + L_i + C_i)/3`, `VWAP_r = Σ TP_i·V_i / Σ V_i` (`indicators/vwap.py`).
  Bu **trade-level VWAP emas**, 5m OHLCV'dan olingan taxmin. B faqat A ishlamasa ishlatiladi.
- **OPEN-D2:** A yoki B. Tanlov natija ko'rmasdan qilinadi va o'zgartirilmaydi.
- Ochilish auksionining (opening cross) bar 0 ga kirishi **NOT VERIFIED**.
- `Σ V = 0` bo'lsa `VWAP_r` aniqlanmagan → o'sha bar va undan oldingi barlarda signal yo'q.

### 1.2 Reclaim setup

```
below_i  ≡  C_i < VWAP_i
above_i  ≡  C_i > VWAP_i
```

**Setup bar `r`** quyidagilarning hammasi bajarilsa:

1. `r ≥ K` va `below_{r−K}, …, below_{r−1}` hammasi true (ketma-ket `K` ta tugallangan bar close VWAP ostida).
2. `above_r` (bar `r` close VWAP ustida; `C_r = VWAP_r` reclaim emas).
3. `CloseTime_d − τ_r ≥ 60 daqiqa` (oxirgi kirish vaqti; normal kunda `t_r ≤ 14:55`).
4. `r` — shu symbol-sessiyada 1–3 shartlarni bajaradigan **eng kichik** indeks. Har symbol-sessiyada **ko'pi bilan
   bitta setup** (u trade bo'ladimi yoki bekor bo'ladimi, farqi yo'q).

| Parametr | Baseline | Status | Asos |
|---|---|---|---|
| `K` (VWAP ostidagi barlar soni) | 3 (= 15 daqiqa, bitta 15m bar) | PROPOSED | "reclaim" uchun avval narx haqiqatan VWAP ostida turgan bo'lishi kerak; 1 bar shovqin. 15m kontekst timeframe bilan bir xil davomiylik. Natijadan tanlanmagan |
| Close VWAP ustida bo'lishi yetarlimi | ha, `C_r > VWAP_r`, `ε = 0` | PROPOSED | minimal baseline; `ε > 0` qo'shimcha parametr |
| Body tasdig'i (`C_r > O_r`) | yo'q | variant V-body | qo'shimcha erkinlik darajasi |
| Volume tasdig'i | yo'q | variant (§1.4 RVOL) | |
| Oxirgi kirish oynasi 60 daq. | PROPOSED | | forced exit'gacha kamida 11 bar; DAY-11 ham vaqt oynasini sinagan → provenance MIXED |
| Bir sessiyada bitta setup | PROPOSED | | "reclaim" ta'rifi bo'yicha birinchi hodisa; DAY-10 bilan mos keladi → provenance MIXED |

Signal **faqat tugallangan bar** asosida hosil bo'ladi (`τ_r` dan keyin).

### 1.3 Confirmation variantlari (metodologik baholash; natijaga qaramasdan)

| Variant | Ta'rif | Afzallik | Kamchilik | Overfitting xavfi |
|---|---|---|---|---|
| **C0 (baseline)**: tasdiqsiz, keyingi bar open | entry = `O_{r+1}` market | eng kam taxmin; intrabar fill noaniqligi yo'q; lookahead tuzilishan imkonsiz | soxta reclaim'larni filtrlamaydi | eng past (0 qo'shimcha parametr) |
| C1: keyingi 5m bar high breakout | bar `r+1` tugagach, buy-stop `H_{r+1}+tick` bar `r+2..` da | ikki barlik momentum | entry 10+ daq. kechikadi; intrabar fill taxmini kerak; 1 qo'shimcha bar | o'rta (amal muddati parametri) |
| C2: keyingi bar close VWAP ustida | `C_{r+1} > VWAP_{r+1}` bo'lsa `O_{r+2}` da kirish | "hold" tasdig'i, fill noaniqligi yo'q | kechikish; stop masofasi kattalashadi | past |
| C3: reclaim bar high breakout | buy-stop `T = H_r + tick`, bar `r+1..r+W` da amal qiladi | narx yo'nalishni tasdiqlagandagina kirish | 5m bar ichidagi fill taxmini (`max(O_b, T)`); `W` parametri | o'rta |
| C4: 15m trend tasdig'i | §1.4 F2 | yuqori timeframe konteksti | 15m bar tugashini qat'iy hisobga olish kerak (leakage xavfi) | o'rta (EMA uzunligi, ta'rif) |

**Taklif:** C0 baseline. C2 va C3 alohida oldindan ro'yxatdan o'tkazilgan variant sifatida (OPEN-D3). Variantlar
soni oldindan cheklanadi va hammasi hisobotda ko'rsatiladi (multiple-testing nazorati, §5.1 #13).

### 1.4 Filterlar

Baseline'da filter **yo'q**. Har biri faqat alohida variant sifatida qo'shilishi mumkin.

| ID | Filter | Formula / ta'rif | Data | Mavjudligi | Lookahead xavfi | Baseline'ga kerakmi |
|---|---|---|---|---|---|---|
| F1 | SPY/QQQ kontekst | `C^{SPY}_r > VWAP^{SPY}_r` (bir xil bar `r`, tugallangan) | SPY, QQQ 5m SIP | **YO'Q** (acquisition kerak) | o'rta: indeks bari ham `τ_r` da tugagan bo'lishi shart; timestamp moslashuvi | yo'q. DAY-08/08B "NOT VALIDATED" (MIXED) |
| F2 | 15m trend | 15m barlar 5m dan agregatsiya: `bar15_j = agg(bar5_{3j..3j+2})`. `r` da faqat `3j+2 ≤ r` bo'lgan `j` ishlatiladi. Trend: `C15_{j*} > EMA20(C15)_{j*}`, `j* = max{j : 3j+2 ≤ r}` | 5m (agregatsiya) | bor (agregatsiya orqali) | **yuqori**: label 09:45 bo'lgan 15m bar 10:00 da tugaydi. Alpaca 15Min ishlatilsa ham shu qoida. 15m ni 5m dan agregatsiya qilish yagona manba va qat'iy tugash qoidasini beradi; Alpaca 15Min faqat data-check sifatida | OPEN-D4 (draft 15m'ni kontekst timeframe deb ataydi). EMA uzunligi 20 PROPOSED; sessiya boshida yetarli 15m bar yo'qligi uchun oldingi sessiyalar 15m barlari ishlatiladi (RTH-only) |
| F3 | Relative Volume | `RVOL_r = CumV_d(r) / mean_{s=1..20} CumV_{d−s}(r)`, `CumV_d(r) = Σ_{i≤r} V_i` (time-of-day). Shart: `RVOL_r ≥ θ` | 5m, 20 sessiya warmup | bor | past (faqat o'tgan sessiyalar va tugallangan barlar) | yo'q. `θ` OPEN; DAY-01 RVOL≥2 ishlatgan va fail bo'lgan (MIXED) |
| F4 | Previous Day High/Low | `PDH_d = max_i H_{d−1,i}`, `PDL_d = min_i L_{d−1,i}` (oldingi sessiya RTH). Masalan, `C_r < PDH_d` (qarshilikkacha joy bor) | 5m | bor | past | yo'q; target/stop bilan o'zaro ta'siri murakkab |
| F5 | Support/resistance | — | — | — | — | **rad etiladi**: obyektiv, oldindan aniqlangan formula yo'q (`levels/support_resistance.py` mavjud, lekin parametrlari ko'p, D1 uchun baholanmagan) |
| F6 | Earnings / catalyst | earnings kunini chiqarib tashlash yoki faqat catalyst kunlari | source-verified tarixiy earnings kalendari | **BLOCKED** (faqat 2026-07..09, ORB uchun) | kalendarning o'zi PIT bo'lishi kerak (sana e'lon qilingan vaqtda ma'lum bo'lganmi) | yo'q. Taxminiy kalendar yaratilmaydi. Gap% (`O_{d,0}/C_{d−1,last} − 1`) data'dan hisoblanadi, lekin u catalyst emas, faqat proxy (DAY-06 → MIXED) |

### 1.5 Entry, stop, target, exit (baseline)

**Entry (C0):**
- `P_ref = C_r` (signal paytidagi reja narxi).
- Stop: `S = min_{i ∈ [r−K, r]} L_i − tick` (VWAP ostidagi spell va reclaim bar ichidagi eng past nuqta).
- Bekor qilish shartlari (bar `r+1` ochilishigacha ma'lum bo'lganlar):
  - `P_ref − S ≤ 0` → setup yo'q.
  - **Minimal stop masofasi:** `δ_ref = (P_ref − S)/P_ref < δ_min` → setup bekor (stop kengaytirilmaydi).
- Order: market, bar `r+1` ochilishida. Fill: `E = O_{r+1}` (+ xarajat, §1.6).
- Agar `O_{r+1} ≤ S` → trade yo'q (gap stop ostida).
- Signal amal qilish muddati: **faqat bar `r+1`**. Bar `r+1` mavjud bo'lmasa (missing bar) → bekor.

**`δ_min` uchun a priori asos (OPEN-D5):** 5 bps/side xarajatda bir round trip R birligida
`cost_R ≈ 2s / δ`. `δ = 0.25%` → 0.40R; `δ = 0.5%` → 0.20R; `δ = 1%` → 0.10R. Bu arifmetika, natija emas.
Taklif: `δ_min = 2s / κ`, bu yerda `κ` = R ning xarajatga ketishi mumkin bo'lgan maksimal ulushi (masalan
`κ = 0.2` → 5 bps'da `δ_min = 0.5%`). `κ` qiymati OPEN. Eslatma: DAY-05 tor stoplar zararini ko'rgan, shuning uchun
bu qoida provenance jihatidan **MIXED**; asosiy argument esa xarajat arifmetikasi.
Muqobil: `δ_min` o'rniga `P_ref − S ≥ k_atr · ATR14_5m(r)` (ATR Wilder, 5m, sessiyalar bo'ylab RTH). OPEN.

**Pozitsiya hajmi:** §3 formulasi, `P_ref` va `S` bilan hisoblanadi (order ochilishdan oldin yuboriladi).
Realizatsiya qilingan R fill narxidan: `R_ps = E − S`.

**Take-profit:** `TP = E + m · (E − S)`, `m = 2` (PROPOSED, OPEN-D6). Limit sell.
**Trailing stop:** baseline'da **yo'q** (variant).
**Partial exit:** baseline'da **yo'q**.
**Majburiy exit:** oxirgi bar ochilishida (`CloseTime − 5 daqiqa`; normal kun 15:55, qisqa kun 12:55) market.
Overnight pozitsiya **yo'q**.

**Bar bo'yicha exit algoritmi** (pozitsiya ochiq bo'lgan har bir bar `b ≥ r+1`, tartib bilan):

```
agar b > r+1 va O_b ≤ S          → exit = O_b                (gap stop ostida; stop narxi kafolat emas)
aks holda agar b > r+1 va O_b ≥ TP → exit = TP                (konservativ: open yaxshiroq bo'lsa ham TP)
aks holda agar L_b ≤ S va H_b ≥ TP + tick → exit = S         (STOP_FIRST: ikkalasi ham tegsa stop)
aks holda agar L_b ≤ S            → exit = S
aks holda agar H_b ≥ TP + tick    → exit = TP                (limit fill uchun narx TP dan o'tishi kerak)
aks holda agar b = majburiy exit bari → exit = O_b
```

- Bar `r+1` (entry bari): fill ochilishda, shuning uchun bar ichida stop/target tekshiriladi (2–5 qatorlar).
- Stop fill narxi `S` dan **yomonroq** bo'lishi mumkin; §1.6 slippage stop fill'larga qo'shimcha qo'llanadi.
- Ochiq pozitsiya paytida bar yo'q (missing) bo'lsa: keyingi mavjud barning ochilishida yuqoridagi algoritm.
  Sessiyada missing bar ko'p bo'lsa — data-quality qoidasi (§5.1 #4).

### 1.6 Xarajatlar va slippage (PROPOSED)

- Loyiha konvensiyasi: per-side `s ∈ {0, 5, 10} bps` notional'ga, 5 bps — asosiy, 10 bps — stress
  (`artifacts/day16/research-protocol-v2.md` §9; v1.1 bilan bir xil).
- D1 qo'shimchasi: **market va stop fill'larga** qo'shimcha noqulay slippage `x ∈ {0, 5, 10, 20} bps` —
  faqat sensitivity jadvali sifatida, gate'da emas. Limit (TP) fill'larga qo'shimcha slippage yo'q,
  lekin `H_b ≥ TP + tick` talabi bor.
- Komissiya per-side stavkaga kiritilgan. Spread alohida modellashtirilmaydi (konvensiya). OPEN-D7: alohida
  spread modeli kerakmi.

---

## 2. S1 — `S1-DAILY-TREND-PULLBACK` (Phase 3)

### 2.0 Belgilar, narx asosi va lookahead

- Sessiya indeksi `k` (XNYS). Raw OHLC: `O_k, H_k, L_k, C_k`. Signal sessiya `k` yopilgandan keyin; order
  `k+1` ochilishidan oldin; fill `k+1` yoki keyin. Qaror `k` hech qachon `k` narxida fill bo'lmaydi
  (protocol v2 §8.5 bilan bir xil).
- **Narx asosi (protocol v2 §3.4 ga mos):** execution va accounting faqat **raw** narxda. Alpaca
  `adjustment=all` **ishlatilmaydi**: u `k` dan keyingi corporate action'larni o'z ichiga oladi (lookahead).
- **Indikatorlar uchun PIT split-adjusted seriya** (har bir signal sessiyasi `k` uchun alohida):

```
X^(k)_j = X_j / Q(j, k),   j ≤ k,   X ∈ {O, H, L, C}
Q(j, k) = Π q(e),  e ∈ (j, k] bo'lgan split ex-date'lar (q > 1 forward split)
```

  Faqat `k` gacha kuchga kirgan split'lar ishlatiladi. Indikator qiymatlari `k` dagi raw narx birliklarida bo'ladi,
  shuning uchun stop/trigger darajalari to'g'ridan-to'g'ri raw narxda.
- Dividendlar indikator darajalarini **o'zgartirmaydi** (baseline). Muqobil: PIT total-return seriya (v2 §3.4). OPEN-S1.
- Implementatsiya eslatmasi: SMA, EMA, ATR narxga nisbatan 1-darajali bir jinsli. Shu sababli `k` da split
  bo'lsa, oldingi indikator qiymatini `q(k)` ga bo'lib, keyin yangi bar bilan yangilash mumkin. Test: to'liq qayta
  hisoblash bilan bir xil natija (§6).

### 2.1 Trend

```
SMA_n(k)   = (1/n) Σ_{j=k−n+1..k} C^(k)_j
Slope50(k) = SMA_50(k) − SMA_50^(k)(k−10)      # ikkalasi ham as-of-k birliklarida
TREND(k)   = [C_k > SMA_200(k)] ∧ [SMA_50(k) > SMA_200(k)] ∧ [Slope50(k) > 0]
```

| Parametr | Baseline | Status |
|---|---|---|
| SMA uzunliklari 50/200 | draftda berilgan | draft parametri |
| Slope oynasi 10 sessiya | PROPOSED | taxminan 2 hafta; natijadan tanlanmagan |
| Warmup | 200 + 10 = 210 sessiya | birinchi signal 210-sessiyadan |

### 2.2 Pullback

```
EMA_21(k) : α = 2/22, birinchi qiymat = SMA_21
ATR_14(k) : Wilder, TR_j = max(H_j − L_j, |H_j − C_{j−1}|, |L_j − C_{j−1}|) (as-of-k), RMA α = 1/14,
            birinchi qiymat = 14 ta TR ning o'rtachasi
PB(k) = [L_k ≤ EMA_21(k)] ∧ [L_{k−1} > EMA_21(k−1)] ∧ [C_k > SMA_50(k)]
```

- 1-shart: EMA21 ni **test qilish** (low unga tegadi yoki ostiga tushadi).
- 2-shart: **birinchi tegish** (kecha low EMA21 ustida edi). Narx EMA21 atrofida aylanib yurganda takroriy signallarni
  oldini oladi.
- 3-shart: pullback trendni buzmagan (close SMA50 ustida).
- "Support zonaga qaytish" **rad etiladi** (obyektiv ta'rif yo'q). "21 EMA'ga yaqinlashish" (`L_k ≤ EMA21 + b·ATR`)
  — variant V-near (qo'shimcha parametr `b`).
- Pullback chuqurligi `Depth(k) = (max_{j=k−9..k} H^(k)_j − L_k) / ATR_14(k)` — **faqat tavsifiy** (hisobotda
  ko'rsatiladi), filter emas.

**Signal candle:** `SIG(k) = TREND(k) ∧ PB(k)`.

### 2.3 Confirmation

| Variant | OHLC formulasi | Baholash |
|---|---|---|
| **Baseline: signal candle high breakout** | trigger `T = H_k + tick`, buy-stop(-limit), keyingi sessiyalarda | obyektiv; tasdiq narxning o'zidan keladi; pattern parametri yo'q |
| Hammer | `body = |C−O|`, `range = H−L > 0`; `min(O,C) − L ≥ 2·body`, `H − max(O,C) ≤ 0.25·range`, `body > 0` | koeffitsientlar (2, 0.25) ixtiyoriy; adabiyotda bir xil ta'rif yo'q → variant |
| Bullish engulfing | `C_{k−1} < O_{k−1}`, `C_k > O_k`, `O_k ≤ C_{k−1}`, `C_k ≥ O_{k−1}` | daily'da gap tufayli kam uchraydi; variant |

Hammer/engulfing faqat baseline'ga **qo'shimcha shart** sifatida (breakout baribir kerak), alohida variantlar.

### 2.4 Entry

- Trigger: `T = H_k + tick` (raw), limit: `T_lim = T + g · ATR_14(k)`, `g = 0.5` (PROPOSED). Order turi:
  buy-stop-limit.
- Amal muddati: sessiyalar `k+1 … k+W`, `W = 3` (PROPOSED, OPEN-S2).
- Bekor qilish (fill bo'lmagan holat):
  - `W` sessiya o'tdi;
  - fill bo'lmagan sessiyada `C_t ≤ S` (pullback struktura buzildi), keyingi sessiyadan bekor;
  - yangi `SIG(k')` (`k' > k`) — yangi trigger eskisini almashtiradi (`T`, `S` qayta hisoblanadi);
  - symbol eligible emas (Sharia, data).
- Sessiya `t` dagi fill (daily OHLC, qaror qoidasi):

```
agar O_t > T_lim                → shu sessiyada fill YO'Q (konservativ; bar ichidagi qaytishni ko'rib bo'lmaydi)
aks holda agar O_t ≥ T          → E = O_t                (gap trigger ustida, lekin limit ichida)
aks holda agar H_t ≥ T          → E = T
aks holda                        → fill yo'q
```

- **Katta gap:** `O_t > T_lim` → kirilmaydi (rejalashtirilgan riskdan oshib ketmaslik uchun). Shu sessiyadan keyin
  order amal qilishda davom etadi (`W` ichida).
- Trigger va fill orasida split bo'lsa, `T`, `T_lim`, `S` ex-date'da `q` ga bo'linadi.

### 2.5 Stop, target, exit

```
S   = min_{j=k−4..k} L^(k)_j − b · ATR_14(k),   b = 0.25     (PROPOSED)
R_ps = E − S   (fill narxidan)
TP  = E + m · R_ps,   m = 2                                    (PROPOSED, OPEN-S3)
Time stop: entry sessiyasi t_e dan keyin H_max = 20-sessiyaning ochilishida market exit   (PROPOSED)
```

- Structural stop = oxirgi 5 sessiya low'i (pullback past nuqtasi), ATR buffer bilan.
- Trailing stop: baseline'da **yo'q**. Variant V-trail: `S_t = max(S_{t−1}, max_{j ≤ t−1} H_j − 3·ATR_14(t−1))`,
  faqat yopilgandan keyin yangilanadi va keyingi sessiyadan amal qiladi.
- Partial exit: **yo'q**.

**Sessiya bo'yicha exit algoritmi** (`t > t_e`):

```
agar O_t ≤ S              → exit = O_t     (overnight gap stop ostida: fill stop narxida EMAS, ochilishda)
aks holda agar O_t ≥ TP   → exit = TP      (konservativ)
aks holda agar L_t ≤ S    → exit = S       (H_t ≥ TP bo'lsa ham: STOP_FIRST)
aks holda agar H_t ≥ TP + tick → exit = TP
aks holda agar t = t_e + H_max → exit = O_t (time stop, ochilishda)
```

- **Entry sessiyasida** (`t = t_e`): fill bar ichida bo'lgan. Ketma-ketlik noma'lum, shuning uchun
  `L_{t_e} ≤ S` → exit = `S` (zarar hisoblanadi); target entry sessiyasida **hisoblanmaydi**.
- Overnight gap risk: gap orqali stop ostidan chiqishlar alohida metrika (`R < −1` bo'lgan trade'lar soni va
  yig'indisi, §5.3).

### 2.6 Earnings va corporate actions

| Masala | Taklif | Status |
|---|---|---|
| Earnings oldidan yangi pozitsiya | Taklif: earnings sanasidan oldingi `n` sessiyada entry yo'q | **BLOCKED**: 2016–2022 uchun source-verified, PIT earnings kalendari yo'q. Taxminiy kalendar yaratilmaydi. OPEN-S4: (a) tasdiqlangan manbadan acquisition (alohida ruxsat), (b) earnings qoidasiz baseline va earnings exposure'ni "UNKNOWN" deb e'lon qilish |
| Earnings davomida saqlash | (a) bilan birga hal qilinadi | BLOCKED |
| Split | raw execution; ex-date ochilishidan oldin: `shares ← shares·q`, `S, TP, T, T_lim ← /q`; P&L ta'siri yo'q | v2 §11.2 bilan bir xil |
| Cash dividend | ex-date'da `cash += shares(k−1 close) · d` | v2 §11.2 bilan bir xil |
| Ex-dividend gap stopni urishi | dividend gap'i stopni urishi mumkin; stop dividendga moslashtirilmaydi (baseline). Bunday holatlar alohida sanaladi | OPEN-S5 |
| Boshqa corporate action turlari (merger, spin-off) | ochiq pozitsiya paytida bo'lsa → BLOCKING data review, jimgina e'tiborsiz qoldirilmaydi | v2 §3.4 bilan bir xil |
| Dividend purification | hisoblanmaydi; ledger keyinchalik hisoblash uchun ex-date, shares va dividend summasini saqlaydi | D10 ADVISER_REQUIRED |

---

## 3. Risk management (Phase 4) — ikkala strategiya

**Saqlangan qaror (foydalanuvchi):** bitta trade riski = kapitalning 0.5%.

```
RiskBudget   = Capital_basis × 0.005
PositionSize = floor( RiskBudget / (EntryPrice_plan − StopPrice) )
```

- `EntryPrice_plan − StopPrice > 0` bo'lishi shart; aks holda trade yo'q.
- `EntryPrice_plan`: D1 da `P_ref = C_r`; S1 da `T` (order ochilishdan oldin yuboriladi, shuning uchun hajm
  fill narxidan emas, reja narxidan).
- Butun aksiyalar (`floor`). `PositionSize = 0` → trade yo'q.
- **Cash cheklovi (margin yo'q):** `PositionSize ← min(PositionSize, floor(Cash_avail / (EntryPrice_plan·(1+s))))`.
  Bu yangi risk limiti emas; cash-funded hisobning majburiy natijasi. Cheklov ishlagan trade'lar sanaladi va ularning
  realizatsiya qilingan risk ulushi hisobotda ko'rsatiladi.
  - Arifmetika (natija emas): notional ulushi `= 0.005 / δ`. D1 da `δ = 0.5%` bo'lsa notional = **kapitalning
    100%**, `δ = 0.25%` bo'lsa 200%. D1 da cash cheklovi tez-tez ishlaydi va **bir vaqtda ko'pi bilan 1–2 pozitsiya**
    bo'ladi. Bu limitlar ochiq qolganda ham simulyatsiya deterministik bo'lishi uchun bir vaqtdagi signallarni
    tartiblash qoidasi kerak (OPEN-R3).
- **Cash account settlement (D1 uchun muhim):** US cash hisobida sotuvdan tushgan pul T+1 da settle bo'ladi.
  Settle bo'lmagan pul bilan sotib olib, settle bo'lgunga qadar sotish good-faith violation'ga olib kelishi mumkin
  (broker siyosati, **NOT VERIFIED** — broker bilan tasdiqlanishi kerak). Taklif: D1 simulyatsiyasida har sessiyadagi
  jami buy notional ≤ sessiya boshidagi **settled cash**. PDT qoidasi odatda margin hisoblariga taalluqli; bu
  hujjatda tasdiqlanmagan.
- Stop orqali rejalashtirilgan risk **real zarar uchun kafolat emas**: gap (§1.5, §2.5), slippage va xarajat
  zararni `RiskBudget` dan oshirishi mumkin. Realizatsiya qilingan `R_net < −1` trade'lar alohida hisoblanadi.
- Xarajatlar: §1.6 (D1), protocol v2 §9 konvensiyasi (S1: `s ∈ {0, 5, 10}` bps per side).

**OPEN-R1 (`Capital_basis`):** fixed initial research capital yoki current equity. Taklif sifatida ikkalasi ham
oldindan e'lon qilinadi: **asosiy hisobot fixed initial capital** (trade'lar orasida R taqqoslanadigan bo'ladi,
compounding natijani buzmaydi), current equity — ikkinchi darajali. Yakuniy tanlov foydalanuvchiga tegishli.

**OPEN DECISION (foydalanuvchi tasdiqlamaguncha belgilanmaydi):**

| ID | Limit |
|---|---|
| OPEN-R2a | Kunlik maksimal zarar limiti |
| OPEN-R2b | Maksimal portfolio open risk |
| OPEN-R2c | Bir vaqtdagi maksimal pozitsiyalar soni |
| OPEN-R2d | Bitta ticker konsentratsiyasi |
| OPEN-R2e | Sektor konsentratsiyasi |
| OPEN-R2f | Korrelyatsiyalangan pozitsiyalar |
| OPEN-R2g | Maksimal gross exposure (cash cheklovidan tashqari) |
| OPEN-R3 | Bir vaqtda bir nechta signal bo'lsa tartib (masalan ticker alfavit tartibida — natijaga bog'liq bo'lmagan deterministik qoida) |

Bu limitlarsiz research run faqat "limitsiz, cash-cheklovli" deb belgilanadi.

---

## 4. Sharia muvofiqligi (Phase 5)

**Bu hujjat diniy fatvo emas.**

| Cheklov | Holat | Manba |
|---|---|---|
| Long-only | D1 va S1 dizayni bo'yicha | ushbu hujjat |
| Cash-funded, margin yo'q | §3 cash cheklovi | D15 PROVISIONAL |
| Short selling, CFD, options, futures yo'q | order yo'li ularni rad etishi kerak | D15 |
| Stock lending'dan voz kechish, idle cash'ga foiz yo'q | broker checklist (hali yo'q) | D15 |
| Aksiya darajasidagi screening | Akinda `/compliance` (`AKINDA_COMPLIANCE_API_V1`), owner qarori D13-A | `docs/shariah/AKINDA_PROVIDER_DECISION.md` |
| Noaniq natija | `DOUBTFUL`, `UNQUALIFIED`, `ERROR_DATA`, `INCOMPLETE_DATA`, noma'lum → `UNVERIFIED` (tradable emas). Hech qachon avtomatik halal emas | `AKINDA_PROVIDER_DECISION.md`; D14 |
| Hozirgi registry | `config/sharia_eligibility.csv` **faqat header** → hozir hech qaysi ticker tradable emas | FACT |
| Akinda ishlatilishi | 1 ta run (AAPL, `HALAL`, `last_scanned` 2026-08-06, `valid_days = 1`); registry'ga ko'chirilmagan | `screening_evidence/akinda/runs/20261017T065808Z/summary.json` |
| Akinda metodologiyasi | vendor o'zini "AAOIFI-aligned", "Not a fatwa", AAOIFI bilan bog'liq emas deb ta'riflaydi; versiya maydoni yo'q. **Mustaqil tasdiqlanmagan** | `AKINDA_PROVIDER_DECISION.md` |
| Tarixiy (PIT) screening | **imkonsiz**: Akinda faqat joriy verdikt beradi. Tarixiy research universe screen qilinmagan | strategy review §2.4 #3 |
| Universe'dagi ehtimoliy nomuvofiq nomlar | masalan JPM (konvensional bank; D9 vaqtinchalik ro'yxat) — tekshirilmagan | INF; OPEN-SH3 |
| Day trading ruxsati (qabd/daman, T+1) | **ADVISER_REQUIRED (D12)**: D1 faqat research/paper; live intraday order kodi qo'shilmaydi | `AAOIFI_MVP_DECISIONS.md` D12 |
| Grace period (holatni yo'qotganda) | D2 PROVISIONAL: yangi kirish yo'q, ochiq pozitsiya keyingi sessiyada yopiladi. **S1 uchun multi-day exit logikasi hali yo'q** | D2 |
| Dividend purification | **ADVISER_REQUIRED (D10)**; S1 ledger kerakli ma'lumotni saqlaydi, summa hisoblanmaydi | D10 |
| Intraday foyda purification | **ADVISER_REQUIRED (D11)** | D11 |
| Akinda litsenziyasi | repo public; registry'ga commit qilingan qatorlar vendor verdiktini qayta tarqatadi → avval litsenziyani tekshirish | `AKINDA_PROVIDER_DECISION.md` |

**Research oqibati:** D1/S1 tarixiy natijalari Sharia-screened bo'lmaydi va "research-only" deb belgilanadi.
Har qanday forward/paper bosqich faqat registry'da amal qiluvchi `COMPLIANT` qatori bor ticker'larda ishlaydi.

---

## 5. Research protocol draftlari (Phase 6–7)

### 5.1 D1 protocol draft (`D1-VWAP-RECLAIM`, PROPOSED)

| # | Element | Taklif | Status |
|---|---|---|---|
| 1 | Universe | `config/day_universe.py::FROZEN_DAY_UNIVERSE` (25), static. Hindsight-selected, survivorship ochiq (v2 §2) | PROPOSED; muqobil OPEN-G3 |
| 2 | Universe selection date | ro'yxat 2026-09-28 commit qilingan (`dcebe47`); tarixiy tanlov vaqti NOT RECORDED. PIT emas | FACT |
| 3 | Data / timeframe | Alpaca SIP 5Min (+ 15m 5m'dan agregatsiya), `adjustment=raw`, RTH, `acquisition/v1_1` kontrakt naqshi, **yangi** snapshot | acquisition **ruxsat berilmagan** |
| 4 | Snapshot / hash | write-once snapshot, per-file SHA-256, manifest SHA-256, `run.json` (request ID'lar), v1.1 integrity tekshiruvlari (78/42 bar grid, NaN yo'q, OHLC izchilligi) | PROPOSED |
| 5 | Corporate actions | intraday, overnight yo'q → sessiya ichida split ta'siri yo'q. `raw`. Split kuni RVOL/PDH/ATR oldingi sessiyalari `Q` ga bo'linadi | PROPOSED |
| 6 | Split (OPEN-D1) | **Variant A (tavsiya):** warmup 2018-12 (20 sessiya) → **train 2019-01-02 → 2020-12-31**, **validation 2021-01-04 → 2021-12-31**, **historical test 2022-01-03 → 2022-12-30** (bir martalik). Keyin **confirmatory forward**: freeze commit'dan keyin, `fwd-gate2` baholangandan keyin. **Variant B:** 2023–2025 ni ham qo'shish (V2 holdout davri; Stage H snapshot'i ishlatilmaydi, yangi intraday acquisition). Har ikkalasida 2026-06-03 → 2026-10-07 intraday **taqiqlanadi** (ifloslangan) | OPEN |
| 7 | Signal | §1.2, C0 | PROPOSED |
| 8 | Execution | §1.5 | PROPOSED |
| 9 | Xarajat | §1.6 | PROPOSED |
| 10 | Risk | §3 | 0.5% DECIDED; qolganlari OPEN |
| 11 | Metrikalar | §5.3 | PROPOSED |
| 12 | Minimal sample | §5.4 | PROPOSED |
| 13 | Accept/reject | §5.5; oldindan ro'yxatdan o'tgan variantlar soni ≤ 3 (C0, C2, C3) va hammasi hisobotda; ko'p taqqoslash uchun Holm tuzatishi | PROPOSED |
| 14 | Reproducibility | §5.6 | PROPOSED |

**D1 qo'shimcha cheklov:** live intraday trading D12 hal bo'lmaguncha mumkin emas, research PASS bo'lsa ham.

### 5.2 S1 protocol draft (`S1-DAILY-TREND-PULLBACK`, PROPOSED)

| # | Element | Taklif | Status |
|---|---|---|---|
| 1 | Universe | `FROZEN_DAY_UNIVERSE` (25), static; SPY faqat benchmark/regime varianti | PROPOSED; OPEN-G3 |
| 2 | Selection date | yuqoridagi kabi | FACT |
| 3 | Data / timeframe | Alpaca SIP 1Day raw + corporate-action event'lar | — |
| 4 | Snapshot | **Stage R** `stage_r_20261007T093410Z`, manifest `aefef19d…6bd` (2026-11-02 da qayta tekshirildi), review `v2.0.4` | lineage: PASS. **Yangi strategiya uchun ishlatish ruxsati: aniq emas → OPEN-S6.** Ruxsat berilmaguncha ishlatilmaydi |
| 5 | Corporate actions | §2.0, §2.6; Stage R event normalizatsiyasi (v2.0.1 C3) | PROPOSED |
| 6 | Split | Stage R ichida (agar ruxsat berilsa): warmup 2016-01-04 → 210-sessiya; **train → 2019-12-31**; **validation 2020-01-02 → 2020-12-31**; **historical test 2021-01-04 → 2022-12-30** (bir martalik). **Ogohlantirish:** Stage R da V2 oilalari natijalari (yil va symbol bo'yicha) e'lon qilingan va mualliflar bu davrni biladi. Shu sababli tarixiy test **pseudo-OOS, blind emas**. **Haqiqiy OOS faqat forward** (OPEN-G2). Stage H (2021-01-04 → 2026-06-02) **ishlatilmaydi** | OPEN |
| 7 | Signal | §2.1–2.3 | PROPOSED |
| 8 | Execution | §2.4–2.5 | PROPOSED |
| 9 | Xarajat | 0 / 5 / 10 bps per side (v2 §9 konvensiyasi) | PROPOSED |
| 10 | Risk | §3 | 0.5% DECIDED; qolganlari OPEN |
| 11 | Metrikalar | §5.3 | PROPOSED |
| 12 | Minimal sample | §5.4 | PROPOSED |
| 13 | Accept/reject | §5.5; variantlar ≤ 3 (baseline, V-trail, V-near) | PROPOSED |
| 14 | Reproducibility | §5.6 | PROPOSED |

**S1 qo'shimcha cheklov:** multi-day Sharia exit logikasi (D2) va earnings siyosati (OPEN-S4) hal bo'lmaguncha
paper/live yo'q.

### 5.3 Metrikalar

Ta'riflar (har bir trade `n` uchun): `PnL_net,n = N_n·(Exit_n − E_n) − costs_n`;
`R_net,n = PnL_net,n / (N_n · R_ps,n)`.

| Metrika | Ta'rif | D1 | S1 |
|---|---|---|---|
| Net expectancy (R) | `mean(R_net)` — **asosiy** | ✓ | ✓ |
| Profit factor | `Σ PnL_net⁺ / |Σ PnL_net⁻|` | ✓ | ✓ |
| Max drawdown | equity egri chizig'i (fixed capital accounting), cho'qqidan pastgacha % | ✓ | ✓ |
| Total trades | | ✓ | ✓ |
| Net return after costs | segment bo'yicha | ✓ | ✓ |
| Win rate, avg win / avg loss (R) | | ✓ | ✓ |
| Max consecutive losses | | ✓ | ✓ |
| Ticker konsentratsiyasi | eng yaxshi 1/2/5 ticker'ning musbat PnL ulushi; HHI | ✓ | ✓ |
| Kun / yil / rejim breakdown | rejim = SPY close > SPY SMA200 (as-of-k), **faqat tavsifiy** | ✓ | ✓ |
| Time-of-day | setup bar `t_r` bo'yicha 30 daqiqalik bucket'lar | ✓ | |
| Session duration | entry'dan exit'gacha barlar soni; bitta barda tugagan trade'lar ulushi | ✓ | |
| Slippage sensitivity | §1.6 `x` jadvali | ✓ | |
| Cash cheklovi ishlagan trade'lar va realizatsiya qilingan risk ulushi | | ✓ | ✓ |
| Holding period | sessiyalar | | ✓ |
| Overnight gap zararlari | `R_net < −1` bo'lgan trade'lar soni va yig'indisi | | ✓ |
| Earnings exposure | earnings'ni kesib o'tgan pozitsiyalar | | BLOCKED (OPEN-S4) |
| Sektor breakdown | sektor xaritasi repo'da yo'q → kerak bo'lsa alohida, versiyalangan xarita | | OPEN |
| Benchmark | equal-weight buy-and-hold (B1) va SPY (faqat ma'lumot uchun) | ✓ | ✓ |

### 5.4 Minimal sample — asoslash (ASSUMPTION-based arifmetika, data ishlatilmagan)

Mean R ni nol bilan solishtirish uchun t-statistika `t ≈ μ·√n / σ`. `t ≥ 2` uchun `n ≥ (2σ/μ)²`.
2R targetli tizimda `σ_R` taxminan 1–1.5R (ASSUMPTION). `σ = 1.2R` da:

| Haqiqiy `μ` (R) | Kerakli `n` |
|---|---|
| 0.20 | ≈ 144 |
| 0.10 | ≈ 576 |
| 0.05 | ≈ 2,304 |

- D1: trade'lar sessiya ichida korrelyatsiyalangan (bir xil bozor harakati) → **sessiya bo'yicha clustered**
  standart xato yoki block bootstrap; samarali `n` trade'lar sonidan kichik.
- S1: 25 symbolda yiliga ehtimoliy trade soni noma'lum. Kam bo'lishi mumkin. Agar validation'da `n` kichik bo'lsa,
  natija **INCONCLUSIVE** deb belgilanadi, PASS emas.
- `n_min` qiymati OPEN-G4. Taklif: `μ = 0.10R` ni aniqlash uchun kerak bo'lgan `n` (≈ 576), oldindan qayd etiladi.

### 5.5 Acceptance / rejection tuzilmasi (barcha chegaralar PROPOSED — REQUIRES APPROVAL)

**A. Metodologik (bittasi bajarilmasa → HARD FAIL, iqtisodiy baholash qilinmaydi):**
1. §6 dagi barcha no-lookahead va execution testlari o'tgan.
2. Snapshot integrity (manifest hash) mos keladi.
3. Taqiqlangan oynalar (D1: 2026-06-03 → 2026-10-07 intraday; S1: Stage H; ikkalasi: ≥ 2026-10-08 forward)
   o'qilmaganligi avtomatik tekshirilgan.
4. `n ≥ n_min`, aks holda INCONCLUSIVE.

**B. Iqtisodiy (validation va bir martalik test segmentlarida):**
1. 5 bps'da `mean(R_net) > 0`, bir tomonlama 95% bootstrap CI pastki chegarasi > 0 (D1: sessiya bo'yicha
   cluster; S1: oy bo'yicha block).
2. 5 bps'da PF > 1.
3. 10 bps'da `mean(R_net) ≥ 0` (stress).
4. Bitta ticker musbat PnL'ning X% idan oshmaydi (X OPEN).

**Natija belgilari:** `RESEARCH-PASSED`, `RESEARCH-FAILED`, `INCONCLUSIVE`. Tarixiy test hech qachon
"validated" deb atalmaydi. FAIL bo'lgan variant qayta parametrlanmaydi ("rescue" yo'q).

### 5.6 Reproducibility

- Strategiya config'i (barcha parametrlar) JSON'da, SHA-256 bilan, run'dan **oldin** commit qilinadi.
- Snapshot manifest hash'i, kod commit'i, Python/paket versiyalari (`environment.json`) har bir run bilan saqlanadi.
- Deterministik: tasodifiylik yo'q; bootstrap uchun seed config'da.
- Yangi, append-only eksperiment registry (`artifacts/v2-experiment-registry.json` ga **tegilmaydi**). OPEN-G5.
- Har bir run: trade-level CSV (signal vaqti, entry/exit vaqti va narxi, sabab kodi, `N`, `R_ps`, xarajatlar).

### 5.7 Leakage va execution risklari (xulosa)

| Risk | Qayerda | Nazorat |
|---|---|---|
| Tugallanmagan bar ishlatish | D1 5m/15m | qaror `τ_r` dan keyin, fill `r+1` da; 15m faqat `3j+2 ≤ r` |
| 15m label noto'g'ri tushunilishi | D1 F2 | 5m dan agregatsiya; test |
| `adjustment=all` (kelajakdagi corporate action) | S1 | ishlatilmaydi; PIT split-adjustment |
| Kelajakdagi split indikatorga kirishi | S1 | `Q(j,k)` faqat `(j,k]` |
| Intrabar ketma-ketlik | D1, S1 | STOP_FIRST; target faqat `TP + tick` dan o'tganda; S1 entry kunida target hisoblanmaydi |
| Gap orqali stop | D1, S1 | exit = ochilish narxi |
| Universe hindsight / survivorship | ikkalasi | ochiq; e'lon qilinadi |
| Researcher bilimi (V2 natijalari, DAY-05..12 diagnostikasi) | ikkalasi | provenance belgilari; confirmatory faqat forward |
| Earnings kalendari PIT emas | S1 | BLOCKED; taxmin qilinmaydi |
| Forward oyna bilan to'qnashuv | ikkalasi | ≥ 2026-10-08 data olinmaydi (§0.5) |
| Cash account settlement | D1 | settled cash qoidasi (§3) |

---

## 6. Kelajakdagi implementatsiya uchun unit test talablari (kod yozilmagan)

| Soha | Test |
|---|---|
| Indikatorlar | VWAP (A va B) qo'lda hisoblangan fixture bilan; sessiya reset; zero volume → NaN; SMA/EMA/ATR (Wilder seed) ma'lum qiymatlar bilan; split'da PIT scaling = to'liq qayta hisoblash |
| Signal candle tugashi | bar `r` ning qiymatlarini o'zgartirish `r−1` dagi signalga ta'sir qilmasligi; tugallanmagan bar hech qachon ishlatilmasligi |
| No lookahead | **future-mutation test**: `r` (yoki `k`) dan keyingi barlarni tasodifiy o'zgartirish ≤ `r` dagi barcha signal va order'larni o'zgartirmasligi |
| 15m konteksti | 09:45 label'li 15m bar 10:00 dan oldin ishlatilmasligi |
| Entry timing | D1 fill = `O_{r+1}`; S1 buy-stop-limit holatlari (`O > T_lim`, `T ≤ O ≤ T_lim`, `H ≥ T`, fill yo'q) |
| Stop/target collision | bir barda ikkalasi → stop; `H = TP` (o'tmagan) → fill yo'q; S1 entry kunida target yo'q |
| Gap execution | `O ≤ S` → exit = `O`; `O ≥ TP` → exit = `TP` |
| Position sizing | `floor`; `E − S ≤ 0` → 0; cash cheklovi; `PositionSize = 0` → trade yo'q |
| Risk budget | fixed va equity asosi; 0.5% |
| Session chegaralari | qisqa kun (42 bar, 12:55 majburiy exit), DST o'tishi, oxirgi kirish oynasi |
| Corporate actions | split: shares × q, darajalar / q; dividend cash; noma'lum event → BLOCKING |
| Missing / invalid bars | missing entry bari → bekor; ochiq pozitsiyada missing → keyingi bar; NaN, `H < L`, manfiy hajm → data-quality fail |
| Taqiqlangan oynalar | loader taqiqlangan sanalarni rad etishi (fail-closed) |

---

## 7. OPEN DECISIONS (ustuvorlik bo'yicha)

| # | ID | Qaror | Nima bloklanadi |
|---|---|---|---|
| 1 | OPEN-G2 | D1/S1 bo'yicha har qanday acquisition yoki run `fwd-gate2` baholangunga qadar (≥ 2026-12-09 16:15 ET) to'xtatiladimi va undan keyin forward data qachondan ishlatiladi | hammasi |
| 2 | OPEN-S6 | Stage R ni yangi strategiya (S1) uchun qayta ishlatishga ruxsat (lineage PASS; ruxsat hujjatlashtirilmagan) | S1 tarixiy research |
| 3 | OPEN-D1 | D1 tarixiy split: Variant A (2019–2022) yoki B (+2023–2025); confirmatory faqat forward ekanligini tasdiqlash (v1.1 line 311) | D1 acquisition |
| 4 | OPEN-R1 | `Capital_basis`: fixed initial yoki current equity | sizing |
| 5 | OPEN-R2a–g, R3 | Portfolio risk limitlari va signal tartibi | portfolio simulyatsiyasi |
| 6 | OPEN-S4 | Earnings: tasdiqlangan manba acquisition yoki earnings'siz baseline | S1 earnings qoidasi, metrikasi |
| 7 | OPEN-D2..D7 | VWAP formulasi (A/B); confirmation variantlari; 15m kontekst baseline'ga kiradimi; `δ_min`/`κ`; `m`; spread modeli | D1 config freeze |
| 8 | OPEN-S1..S3, S5 | dividend adjustment; `W`; `m`/`H_max`; ex-dividend stop | S1 config freeze |
| 9 | OPEN-G3 | Universe: 25 ta frozen yoki boshqa (masalan, Akinda bilan screen qilingan) | ikkalasi |
| 10 | OPEN-G4 | `n_min` va acceptance chegaralari (§5.5) | gate |
| 11 | OPEN-G5 | Yangi eksperiment registry yo'li | reproducibility |
| 12 | OPEN-G1 | Ushbu spetsifikatsiyani ChatGPT draftlari bilan solishtirish (draftlar repo'da yo'q) | — |
| 13 | OPEN-SH1..3 | D12 (day trading), D10/D11 (purification), universe'dagi aniq nomuvofiq nomlar — adviser / Akinda | D1 live; S1 dividendlar |
