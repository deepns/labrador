"""Text content for labrador-bench. Every person, company and number here is fictional.

Each entry: relative path -> (body, [queries]).
A query is (text, category, extra) where extra may hold {"page": n, "hard": True, "also": [...]}.
"hard" marks a query whose answer has a deliberately similar distractor elsewhere in the folder.
"""

NOTES = {
"notes/engineering/kubernetes-networking.md": ("""# Kubernetes networking cheat sheet

Every pod gets its own IP address. Pods on different nodes reach each other directly through the
CNI plugin (Calico or Cilium in our clusters) without NAT. A Service puts a stable virtual IP in front
of a changing set of pods; kube-proxy or eBPF programs the forwarding rules.

Debugging checklist:
- `kubectl exec -it <pod> -- curl svc-name:8080` to test service DNS from inside the cluster.
- NetworkPolicies are default-allow until the first policy selects a pod; after that it is default-deny.
- If DNS lookups time out, check the CoreDNS pods and the ndots:5 setting in resolv.conf.
""", [("how do pods on different machines reach each other", "text-semantic", {"hard": True}),
      ("why do DNS lookups inside the cluster time out", "text-semantic", {})]),

"notes/engineering/kubernetes-storage.md": ("""# Kubernetes storage notes

PersistentVolumeClaims ask for storage; a StorageClass decides how it is provisioned through a CSI driver.
StatefulSets give each replica its own claim through volumeClaimTemplates, so a database pod keeps its disk
when it is rescheduled. ReadWriteOnce volumes attach to a single node at a time; use ReadWriteMany (NFS or
a file service) when several pods must write the same files.

Resizing: set allowVolumeExpansion: true on the StorageClass, then edit the claim's size. Shrinking is not
supported. Snapshots need the external-snapshotter CRDs installed.
""", [("can a database pod keep its disk when it moves to another node", "text-semantic", {"hard": True}),
      ("how to grow a volume that is running out of space", "text-semantic", {})]),

"notes/engineering/postmortem-2026-03-db-failover.md": ("""# Postmortem: primary database failover, March 9 2026

Impact: checkout was unavailable for 14 minutes (02:10 to 02:24 UTC).

What happened: the primary Postgres node lost its disk. Automatic failover started, but the replica refused
to promote because its replication TLS certificate had expired two days earlier, so it had silently stopped
streaming. On-call promoted the second replica by hand.

Root cause: certificate expiry on the replication channel was not monitored.
Action items: alert 21 days before any certificate expires; run a failover drill every quarter.
""", [("the outage where the standby could not take over because a certificate had expired", "text-semantic", {"hard": True}),
      ("how long was checkout down in March", "text-semantic", {})]),

"notes/engineering/postmortem-2026-07-cache-stampede.md": ("""# Postmortem: cache stampede, July 22 2026

Impact: p99 API latency rose from 180 ms to 4.2 s for 38 minutes; 3% of requests failed.

What happened: a nightly job refreshed the product catalog and set every cache key to expire at exactly
midnight. At 00:00 thousands of requests missed the cache at once and all hit the database together.

Fix: add random jitter of plus or minus 10% to every TTL, and let one request rebuild a hot key while others
serve the stale value (request coalescing).
""", [("the incident where everything expired at the same moment and hammered the database", "text-semantic", {"hard": True}),
      ("why add randomness to cache expiry times", "text-semantic", {})]),

"notes/engineering/vector-search-notes.md": ("""# Vector search notes

Brute force is exact and fine up to about a million vectors on one machine. HNSW builds a layered graph:
fast and high recall, but memory hungry and slow to build. IVF clusters the vectors and only scans the
nearest clusters; pair it with product quantization (IVF-PQ) to shrink memory 10 to 30 times.

Measure recall@10 against brute force before trusting an approximate index. Normalise vectors so the
dot product equals cosine similarity.
""", [("tradeoffs between graph based and cluster based approximate nearest neighbour indexes", "text-semantic", {"hard": True})]),

"notes/engineering/llm-eval-notes.md": ("""# Evaluating LLM features

Start with a golden set of 50 to 200 real user questions with reviewed answers. Track it on every change.
LLM-as-judge is useful for scale, but judges prefer longer answers and their own model family; calibrate the
judge against human labels and report agreement. Separate retrieval failures (the right passage was never
found) from generation failures (it was found but the answer was wrong).
""", [("using a model to grade another model's answers and its biases", "text-semantic", {"hard": True})]),

"notes/engineering/git-cheatsheet.md": ("""# Git rescue cheat sheet

- Find the commit that broke a test: `git bisect start`, `git bisect bad`, `git bisect good v2.3.0`, then let
  `git bisect run pytest tests/test_login.py` do the search.
- Undo a bad rebase: `git reflog` shows where HEAD was; `git reset --hard HEAD@{5}`.
- Split the last commit: `git reset HEAD~1`, then stage and commit in pieces.
""", [("binary search through history to find which change introduced a bug", "text-semantic", {})]),

"notes/engineering/interview-feedback-system-design.md": ("""# Interview feedback: system design, senior candidate (loop 2026-08-14)

Prompt: design a URL shortener for 100M new links a month.
Strong: back-of-envelope sizing, chose base62 keys, put a cache in front of the key-value store, discussed
hot keys. Weak: hand-waved consistency between regions; no plan for abuse and spam links.
Recommendation: lean hire, pair with a follow-up conversation on multi-region data.
""", [("feedback for the candidate who designed a link shortener", "text-semantic", {})]),

"notes/engineering/1on1-priya.md": ("""# 1:1 with Priya, September 2026

- Wants to lead the multimodal ingestion workstream next quarter; agreed to make her the DRI for the
  OCR and PDF parsing pieces.
- Asked for more visibility with the platform staff group; I will invite her to the architecture review.
- Feedback for her: write design docs earlier, before the prototype is half done.
- Follow-up: promo packet discussion in January.
""", [("who wants to own the OCR and PDF parsing work", "text-semantic", {})]),

"notes/engineering/meeting-2026-09-q4-roadmap.md": ("""# Q4 roadmap meeting, September 30 2026

Decisions:
1. Ship multimodal ingestion (images and scanned PDFs) to beta customers by December 5.
2. Deprecate the v1 search API on January 31 2027; send notices in October.
3. Freeze new connector work until the reliability backlog is under 20 tickets.

Risks: GPU capacity for embedding backfills; two senior engineers on leave in November.
""", [("when will the old version one search API be turned off", "text-semantic",
       {"hard": True, "also": ["pdfs/Multimodal search - design review.pdf"]}),
      ("what did we decide about new connectors in Q4", "text-semantic", {})]),

"notes/engineering/security-phishing-incident.md": ("""# Security incident: payroll phishing email, August 2026

An email that looked like it came from the payroll team asked staff to "confirm direct deposit details" on a
look-alike site. Four people clicked; three entered credentials. We reset those three accounts, revoked
their sessions, blocked the sender domain and added a banner for external email. No payroll change was made.
Training refresher scheduled for all staff in September.
""", [("the fake email pretending to be from payroll", "text-semantic", {})]),

"notes/home/sourdough-starter.md": ("""# Sourdough starter routine

Feed once a day at room temperature: 1 part starter, 5 parts flour (half rye, half bread flour), 5 parts water.
It is ready to bake with when it doubles within 4 to 6 hours and smells yeasty, not like nail polish.
Keep it in the fridge between bakes and feed it weekly. The loaf: 75% hydration, 2% salt, 12 hour cold proof.
""", [("how often to feed the jar of wild yeast and in what ratio", "text-semantic", {"hard": True})]),

"recipes/banana-bread.txt": ("""Grandma's banana bread

3 very ripe bananas, mashed (the browner the better)
1/3 cup melted butter, 3/4 cup sugar, 1 egg, 1 tsp vanilla
1 tsp baking soda, pinch of salt, 1.5 cups flour, handful of walnuts

Mix butter into the bananas, then sugar, egg and vanilla. Stir in soda and salt, then flour.
Bake at 350F for about 60 minutes until a toothpick comes out clean.
""", [("a loaf cake that uses up overripe fruit", "text-semantic", {"hard": True})]),

"recipes/palak-paneer.md": ("""# Palak paneer

Blanch 500 g spinach for 2 minutes, plunge into ice water, then blend smooth with 2 green chillies.
Fry cumin seeds, then onion, ginger and garlic until golden; add tomato and cook down.
Add the spinach puree, a pinch of garam masala and salt; simmer 5 minutes.
Fold in 250 g paneer cubes (pan-fried first if you like) and finish with a spoon of cream.
""", [("green curry made from spinach with cottage cheese cubes", "text-semantic", {})]),

"notes/home/espresso-dialing-in.md": ("""# Dialing in espresso

Start with 18 g of coffee in, 36 g of espresso out, in 28 to 32 seconds.
Sour and thin: grind finer. Bitter and harsh: grind coarser or pull a shorter shot.
Change one variable at a time. Light roasts like a longer ratio, about 1:2.5.
""", [("my coffee shots taste sour, what should I change", "text-semantic", {"hard": True})]),

"notes/home/garden-planting-calendar.md": ("""# Vegetable garden calendar (zone 8b)

- February: start tomatoes and peppers indoors under lights.
- March: direct sow peas, spinach and radishes.
- Mid May, after the last frost: plant out tomatoes, squash and beans.
- August: sow fall lettuce and kale. October: plant garlic for next summer.
""", [("when is it safe to move tomato seedlings outside", "text-semantic", {})]),

"notes/home/car-maintenance-log.txt": ("""Car maintenance log - 2019 hatchback

2026-01-18  Oil change, synthetic 0W-20, odometer 45,210 mi
2026-04-02  Tire rotation and alignment, 47,900 mi
2026-06-21  Front brake pads and rotors replaced, 50,115 mi, squeal fixed
2026-09-30  Cabin air filter, wiper blades, 53,480 mi
Next oil change due at 52,710 mi (overdue!)
""", [("when were the brakes last replaced", "text-semantic", {}),
      ("45,210", "text-exact", {})]),

"notes/home/home-wifi-setup.txt": ("""Home network

Router admin page: 192.168.50.1 (admin password is in the password manager, not here)
Mesh nodes: living room, upstairs hallway, garage
Main network: RaoHome-5G
Guest network: RaoGuest  (isolated from the main LAN, resets weekly)
Kids devices: on the RaoKids SSID with a 9pm pause schedule
""", [("what is the name of the guest wifi network", "text-semantic", {}),
      ("RaoKids", "text-exact", {})]),

"notes/home/kids-soccer-schedule.md": ("""# U8 soccer, fall season

Practice: Wednesdays 5:30 pm at Meadowbrook Park, field 3.
Games: Saturdays, 9:00 am kickoff, arrive 30 minutes early.
Snack rotation: Rao family on October 18 and November 15 (orange slices and water, no nuts).
Coach Daniel: text him if the kid is sick.
""", [("which saturdays are we bringing snacks for the team", "text-semantic", {})]),

"notes/home/birthday-party-plan.md": ("""# Ananya's 7th birthday

Theme: dinosaurs. Date: Saturday November 8, 2 to 4 pm, at home.
Guests: 12 kids from class plus cousins. Activities: fossil dig in the sandbox, dino egg hunt.
Cake: chocolate with green frosting, ordered from Sweet Fern Bakery, pick up at 11 am.
Return gifts: small explorer kits.
""", [("plans for the dinosaur themed kids party", "text-semantic", {})]),

"notes/home/moving-checklist.md": ("""# Moving checklist

- Movers booked for June 14 (Bluebird Moving, quote $2,950, two trucks).
- Forward mail at the post office one week before.
- Transfer internet service; schedule install for June 13 at the new place.
- Measure the new living room before deciding on the sectional sofa.
- Return the old apartment keys and get the deposit inspection on June 16.
""", [("what day are the movers coming", "text-semantic", {})]),

"notes/home/solar-panel-quotes.md": ("""# Solar quotes, spring 2026

| Installer | System | Price before credit | Panels | Warranty |
|---|---|---|---|---|
| Brightpath Solar | 8.2 kW | $21,400 | 20 x 410 W | 25 years |
| Cedar Sun Co | 7.6 kW | $19,900 | 19 x 400 W | 25 years |
| Northlight Energy | 8.8 kW | $24,300 | 22 x 400 W | 30 years |

Estimated payback around 9 years with the federal credit. Roof needs inspection first (shingles are 14 years old).
""", [("which installer offered the longest warranty on rooftop panels", "text-semantic", {})]),

"notes/home/tax-checklist-2026.md": ("""# Tax documents checklist

- W-2 from employer (arrives late January)
- 1099-INT from the savings bank, 1099-DIV from the brokerage
- Property tax statement and mortgage interest form 1098
- Childcare receipts for the dependent care FSA claim
- Charity donation receipts over $250 need a written acknowledgment
""", [("which forms do I need to collect before filing taxes", "text-semantic", {})]),

"notes/personal/running-plan-half-marathon.md": ("""# Half marathon plan, 12 weeks

Weeks 1 to 4: three easy runs and one long run, long run 8 to 11 km.
Weeks 5 to 8: add one tempo run of 20 to 30 minutes; long run up to 16 km.
Weeks 9 to 11: long run peaks at 19 km in week 10.
Week 12: taper, two short easy runs, race on Sunday. Practice fueling with gels on every long run.
""", [("how far is the longest training run before the 21 km race", "text-semantic", {})]),

"notes/personal/bike-commute-route.md": ("""# Bike commute

Route: Burke trail to the ship canal, cross at the Fremont bridge, then the protected lane on Westlake.
11.4 km, about 38 minutes. Rain gear in the pannier from October to April.
Locker room in building C opens at 7 am; bring a lock for locker 214.
""", [("which way do I cycle to the office", "text-semantic", {})]),

"notes/personal/book-club-notes.md": ("""# Book club: "The Salt Orchard" (October pick)

A novel about three sisters who inherit a failing apple orchard on a windy coast and disagree about selling it.
Discussion questions: is the eldest sister selfish or protective? What does the storm in chapter 9 change?
Next month: a short story collection, host is Meera.
""", [("the novel about sisters arguing over whether to sell the family farm", "text-semantic", {})]),

"notes/personal/podcast-ideas.txt": ("""Podcast episode ideas

1. Why search is hard: from keyword matching to embeddings, explained with a kitchen drawer analogy.
2. Interview a librarian about how people actually look for things.
3. The history of the filing cabinet.
4. Local-first software: owning your data again.
""", [("episode idea about talking to a librarian", "text-semantic", {})]),

"notes/personal/reading-list-ml.md": ("""# ML reading list

- Matryoshka representation learning: nested embeddings you can truncate.
- ColBERT and late interaction for retrieval.
- Reciprocal rank fusion: combining rankings without score calibration.
- Contrastive image-text pretraining and the modality gap.
""", [("papers on combining several rankings without calibrating scores", "text-semantic", {})]),

"travel/kyoto-trip-2025.md": ("""# Kyoto, three days in April 2025

Day 1: Fushimi Inari before 7 am, thousands of vermilion torii gates up the mountain.
Day 2: Arashiyama bamboo grove, Tenryu-ji garden, then the monkey park. Evening walk in Gion.
Day 3: Kinkaku-ji (the golden pavilion), Ryoan-ji rock garden, lunch at Nishiki market.
Buy an ICOCA card for buses. Cherry blossoms peak the first week of April along the Philosopher's Path.
""", [("temple with a golden pavilion and a bamboo forest walk", "text-semantic", {"hard": True})]),

"travel/lisbon-trip-2026.md": ("""# Lisbon, five days in May 2026

Ride tram 28 early to avoid the crowds; Alfama viewpoints at sunset.
Day trip to Sintra: Pena Palace (book the 9:30 entry), then the Moorish castle walls.
Eat pastéis de nata at the bakery in Belém, grilled sardines in Bairro Alto.
Hotel: Casa do Rio, confirmation 58-QX-2210. Airport to center by metro, red line.
""", [("custard tarts and a hilltop palace day trip", "text-semantic", {"hard": True}),
      ("58-QX-2210", "text-exact", {})]),
}

MULTILINGUAL = {
"recipes/dal-tadka-hindi.md": ("""# दाल तड़का

एक कप अरहर की दाल को धोकर तीन कप पानी, हल्दी और नमक के साथ प्रेशर कुकर में तीन सीटी तक पकाएं।
तड़के के लिए घी गरम करें, उसमें जीरा, हींग, सूखी लाल मिर्च, लहसुन और प्याज़ डालें।
टमाटर डालकर नरम होने तक पकाएं, फिर पकी हुई दाल मिलाएं।
ऊपर से हरा धनिया डालें और चावल या रोटी के साथ परोसें।
""", [("lentils cooked in a pressure cooker with a spiced ghee tempering", "multilingual", {})]),

"travel/madurai-trip-tamil.md": ("""# மதுரை பயணம்

காலையில் மீனாட்சி அம்மன் கோயிலுக்கு சென்றோம். கோபுரங்கள் மிகவும் அழகாக இருந்தன.
மதியம் திருமலை நாயக்கர் மஹாலைப் பார்த்தோம்.
மாலையில் ஜிகர்தண்டா குடித்தோம்.
அடுத்த நாள் ரயிலில் சென்னைக்கு திரும்பினோம்.
""", [("visit to the Meenakshi temple and the palace in Madurai", "multilingual", {})]),

"notes/home/reunion-vecinos-es.md": ("""# Reunión de vecinos, 12 de septiembre

- La recogida de basura pasa al jueves a partir de octubre.
- Se aprobó pintar la valla del parque infantil; cada familia aporta 40 dólares.
- Fiesta de la calle el 4 de octubre: cada casa trae un plato para compartir.
- Próxima reunión: 14 de noviembre en la casa de los Ortega.
""", [("which day will the garbage be collected after the neighborhood meeting", "multilingual", {})]),

"notes/home/appartement-paris-fr.md": ("""# Appartement de Paris - problèmes à régler

Le radiateur de la chambre ne chauffe plus depuis lundi. Le plombier passe jeudi entre 8 h et 12 h.
La serrure de la boîte aux lettres est cassée : demander une nouvelle clé au gardien.
Loyer de novembre : virement à faire avant le 5.
""", [("when is the plumber coming to fix the bedroom heater", "multilingual", {})]),
}

CODE = {
"code/retry_with_backoff.py": ('''import random
import time


def retry(fn, attempts=5, base=0.2, cap=10.0, retry_on=(TimeoutError, ConnectionError)):
    """Call fn, retrying failures with exponential backoff and full jitter."""
    for i in range(attempts):
        try:
            return fn()
        except retry_on:
            if i == attempts - 1:
                raise
            time.sleep(random.uniform(0, min(cap, base * 2 ** i)))
''', [("function that retries a failed network call with growing random delays", "code", {"hard": True})]),

"code/token_bucket.py": ('''import time


class TokenBucket:
    """Allow `rate` operations per second with bursts up to `capacity`."""

    def __init__(self, rate: float, capacity: int):
        self.rate, self.capacity = rate, capacity
        self.tokens, self.updated = capacity, time.monotonic()

    def allow(self) -> bool:
        now = time.monotonic()
        self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate)
        self.updated = now
        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False
''', [("limit how many requests per second a client can make", "code", {"hard": True})]),

"code/debounce.js": ('''// Run `fn` only after `wait` ms have passed without another call (search-as-you-type).
export function debounce(fn, wait = 250) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), wait);
  };
}
''', [("wait until the user stops typing before running the search", "code", {})]),

"code/monthly_revenue.sql": ('''-- Revenue per month for paid orders, last 12 months
SELECT date_trunc('month', o.paid_at) AS month,
       SUM(oi.quantity * oi.unit_price) AS revenue
FROM orders o
JOIN order_items oi ON oi.order_id = o.id
WHERE o.status = 'paid'
  AND o.paid_at >= now() - interval '12 months'
GROUP BY 1
ORDER BY 1;
''', [("query that totals sales by month for the past year", "code", {})]),

"code/backup_photos.sh": ('''#!/usr/bin/env bash
# Nightly: copy new photos to the NAS, keep 30 days of snapshots.
set -euo pipefail
SRC="$HOME/Pictures/Library"
DEST="nas.local:/volume1/backups/photos"
rsync -a --delete --link-dest="../latest" "$SRC/" "$DEST/$(date +%F)/"
ssh nas.local "ln -sfn /volume1/backups/photos/$(date +%F) /volume1/backups/photos/latest"
ssh nas.local "find /volume1/backups/photos -maxdepth 1 -type d -mtime +30 -exec rm -rf {} +"
''', [("script that copies pictures to the network drive every night", "code", {})]),
}

DATA = {
"finance/expenses-2026-09.csv": ("""date,merchant,category,amount_usd
2026-09-01,Greenway Grocery,groceries,142.18
2026-09-02,Cascade Internet,utilities,79.99
2026-09-03,Copperleaf Cafe,dining,14.75
2026-09-05,Metro Transit,transport,50.00
2026-09-08,Greenway Grocery,groceries,96.40
2026-09-11,The Tool Shed,home,63.27
2026-09-14,Paper Moon Books,books,38.50
2026-09-19,Greenway Grocery,groceries,118.02
2026-09-22,Ridge Electric,home,1450.00
2026-09-28,City Water,utilities,88.13
""", [("Metro Transit 50.00", "text-exact", {})]),

"work/oncall-handbook.html": ("""<html><head><title>On-call handbook</title></head><body>
<h1>On-call handbook</h1>
<p>When the pager fires, acknowledge within 5 minutes and post in #incidents.</p>
<p>Check the service dashboard for error rate and p99 latency before changing anything.</p>
<p>For a 503 spike, look at upstream health checks and the load balancer first.</p>
<p>Escalate to the secondary after 20 minutes without mitigation. Keep a timeline as you go.</p>
</body></html>""", [("what to do first when I get paged at night", "text-semantic", {})]),

"work/saved-article-async-communication.html": ("""<html><body><article>
<h1>Writing for async teams</h1>
<p>Lead with the decision you need and the date you need it by. Put context after the ask, not before.</p>
<p>Prefer one long, complete message over five short ones; people in other time zones read in batches.</p>
<p>Record meetings, but always publish written notes: nobody watches a 50 minute recording.</p>
</article></body></html>""", [("advice on writing messages for colleagues in other time zones", "text-semantic", {})]),
}

# Bulk distractors: plausible daily logs that never answer a benchmark query.
STANDUP_TASKS = [
    "fixed a flaky unit test in the billing service", "reviewed the pull request for the export button",
    "paired with Omar on the CSV importer", "updated the onboarding doc for new hires",
    "cleaned up unused feature flags", "investigated a slow query in the reports page",
    "upgraded the logging library", "triaged five new bug reports", "wrote tests for the date parser",
    "demoed the settings page to design", "renamed the user preferences table columns",
    "added pagination to the audit log API", "bumped the Node version in CI",
    "answered support questions about SSO", "refactored the email templates",
    "deleted the old staging environment", "drafted the release notes for 4.12",
]
