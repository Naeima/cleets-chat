"""
scope.py: is a question answerable from the CLEETS knowledge graphs?

CLEETS-CHAT composes every answer from retrieved statements, so a question whose subject
is not in the graphs must be told so rather than answered with whatever retrieval
happens to return (before this check, "What is the capital of France?" produced a
Wales prediction summary and "What is the weather in Cardiff?" listed Cardiff's EV
observations). `check_scope()` runs before any retrieval and returns a short
"not modelled" answer when the question lies outside the graphs, with a one-line
reason, and None when the question can be routed to the normal answerers.

What counts as modelled is read from the loaded graphs wherever the graphs hold it:
district names and aliases (cleets:WelshLAD), the other areas the graph holds and
what it holds for them (cleets:EnglishLAD, population density only), the measure
labels of the observation index, the prediction types (prov:Activity), the dataset
identifiers and publishers (dcat:Dataset) and the ontology terms (owl:Class and
properties). To these the module adds the routing lexicons the answerers already
use (kg_service.MEASURE_KEYWORDS, qa.FAMILY_KEYWORDS, ...) and plain-language
synonyms. A short curated table (UNMODELLED_TOPICS) names subjects stakeholders ask
about that no dataset in the graphs records (prices, emissions, charger speeds, fuel
types, weather, ...), so that the reason can say which dataset would have been
needed. Whatever else survives stop-word removal is reported as an unrecognised term.

Three scope axes are checked, in this order:
  1. thematic  - a curated unmodelled topic; no recognised district, measure,
                 prediction type or provenance term at all; or a district, table or
                 provenance request whose subject is unrecognised ("the weather in
                 Cardiff", "a table of dog ownership");
  2. spatial   - a place outside the 22 Welsh districts (English districts, held with
                 population density only; countries and cities outside the graph);
  3. temporal  - a year before the first observation or beyond the prediction horizon.

Pure Python: it runs unchanged in the browser build (Pyodide) through the snapshot.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

try:
    from kg_service import MEASURE_KEYWORDS, MEASURE_LABELS, ONTOLOGY_URL
except ImportError:  # pragma: no cover - kg_service is always alongside this module
    MEASURE_KEYWORDS, MEASURE_LABELS, ONTOLOGY_URL = [], {}, "https://w3id.org/def/cleets"

# --------------------------------------------------------------------------- lexicons
# Plain-language synonyms for the observed measures, in addition to kg_service.MEASURE_KEYWORDS.
MEASURE_SYNONYMS = [
    ("population", ("people", "person", "persons", "residents", "resident", "inhabitants", "inhabitant", "populace",
                    "headcount", "demographic", "demographics", "how many people", "live", "lives", "living")),
    ("density", ("dense", "densely", "crowded", "sparse", "sparsely", "urban", "rural", "per sq km", "per square",
                 "persons per")),
    ("deprivation", ("deprived", "poverty", "poor", "poorer", "poorest", "wealth", "wealthy", "wealthier", "affluent",
                     "affluence", "rich", "richer", "richest", "disadvantaged", "inequality", "equity", "equitable",
                     "decile", "deciles")),
    ("keepership", ("ev", "evs", "bev", "bevs", "electric car", "electric cars", "electric vehicle",
                    "electric vehicles", "electric", "battery-electric", "battery electric", "keeper", "keepers",
                    "kept", "ownership", "owner", "owners", "owned", "registration", "registrations", "registered",
                    "adopter", "adopters", "adopt", "adopts", "adopted", "adoption", "uptake", "take-up", "takeup",
                    "penetration", "zev", "zevs", "zero emission vehicle", "zero emission vehicles",
                    "zero-emission vehicle", "zero-emission vehicles", "zev mandate", "ulev", "ulevs", "plug-in",
                    "plugin", "electrify", "electrified", "electrification", "electrifies", "electrifying", "private",
                    "privately")),
    ("chargers", ("charger", "chargers", "charging", "chargepoint", "chargepoints", "charge point", "charge points",
                  "charging point", "charging points", "charging station", "charging stations", "charging device",
                  "charging devices", "charging infrastructure", "charging network", "infrastructure", "evci",
                  "public charging", "public", "publicly", "recharge", "recharging", "device", "devices")),
    ("vehicle_stock", ("vehicle", "vehicles", "car", "cars", "fleet", "fleets", "parc", "stock", "licensed vehicles",
                       "motor", "motoring", "motorist", "motorists", "automobile", "automobiles", "private vehicles",
                       "van", "vans")),
    ("ratio", ("ratio", "ratios", "per charger", "keepers per", "per device")),
    ("chargers_per_100k", ("per 100k", "per 100,000", "per 100 000", "per capita", "per resident", "per head",
                           "per person", "per inhabitant")),
    ("evs_per_1000", ("per thousand", "per 1000", "per 1,000")),
]

# Words that mark a question as being about the predictions (qa.FAMILY_KEYWORDS is merged in at run time as well).
PREDICTION_WORDS = (
    "predict", "predicts", "predicted", "prediction", "predictions", "forecast", "forecasts", "forecasting", "forecasted",
    "projection", "projections", "projected", "scenario", "scenarios", "outlook", "future", "expect", "expected",
    "expectation", "estimate", "estimated", "estimates", "trajectory", "trajectories", "horizon", "milestone",
    "milestones", "reach", "reaches", "reached", "cross", "crosses", "crossed", "achieve", "achieves", "achieved", "hit",
    "hits", "target", "targets", "terminal", "all three", "three scenarios", "sensitivity", "sensitive", "assumption",
    "assumptions", "assume", "assumed", "assumes", "model", "models", "modelled", "modeled", "modelling", "modeling",
    "curve", "curves", "logistic", "saturation", "saturate", "saturates", "capacity", "ceiling", "ceilings", "simulate",
    "simulation", "simulated", "by 2045", "in 2045", "penetration", "electrification", "electrify", "transition",
    "quarterly forecasts", "uncertainty", "uncertain", "confidence", "interval", "intervals",
)

# Prediction-type words the answerers route on (qa.FAMILY_KEYWORDS is merged in at run time as well).
FAMILY_WORDS = (
    "turnover", "scrappage", "scrappage age", "phase-out", "phase out", "phaseout", "sales ban", "ban", "bans", "2053",
    "arrival", "arrivals", "residual", "residuals", "ice", "non-bev", "non bev", "age-structured", "structural age",
    "vintage", "vintages", "fleet turnover", "replacement", "replaced", "scrapped",
    "hierarchical", "midpoint", "midpoints", "slowest", "fastest", "slow", "slower", "slowly", "fast", "faster", "quick",
    "quickly", "quickest", "early", "earliest", "earlier", "late", "later", "latest", "diffuse", "diffuses", "diffusion",
    "diffusing", "diffusion rate", "empirical bayes", "bayes", "pooling", "pooled", "shrink", "shrinkage", "shrunk",
    "rate per quarter", "lag", "lags", "lagging", "ahead", "behind",
    "charging constraint", "provision", "binding", "chargers per", "bevs per", "charging provision", "constraint",
    "constraints", "constrained", "adequacy", "adequate", "enough", "sufficient", "shortfall", "shortage", "benchmark",
    "neural", "nn", "gnn", "perceptron", "graph neural", "walk-forward", "walk forward", "mlp", "network", "networks",
    "machine learning", "deep learning", "table 5", "table 6", "table 7", "table 8", "table 9", "table 10",
    "covariate", "covariates", "ridge", "random forest", "extra trees", "leave-one-out", "relate", "relates", "related",
    "relationship", "relationships", "correlate", "correlates", "correlated", "correlation", "correlations", "what makes",
    "explain", "explains", "explained", "explanatory", "driver", "drivers", "factor", "factors", "determinant",
    "determinants", "influence", "influences", "influenced", "effect", "effects", "affect", "affects", "association",
    "associated",
)

# Model-accuracy vocabulary (qa.ACCURACY_KEYWORDS is merged in at run time as well).
ACCURACY_WORDS = (
    "accurate", "accuracy", "accurately", "backtest", "backtests", "back-test", "mae", "rmse", "r2", "error", "errors",
    "baseline", "baselines", "drift", "persistence", "outperform", "outperforms", "beat", "beats", "reliable", "reliability",
    "perform", "performs", "performance", "validation", "validate", "validated", "evaluation", "evaluate", "evaluated",
    "metric", "metrics", "best model", "which model", "what model",
)

# Provenance, dataset and knowledge-graph vocabulary (dataset identifiers, publishers and ontology terms are read from the graph).
PROVENANCE_WORDS = (
    "data", "dataset", "datasets", "data set", "data sets", "source", "sources", "sourced", "cite", "cited", "cites",
    "citation", "citations", "reference", "references", "referenced", "provenance", "evidence", "origin", "come from",
    "came from", "comes from", "derived", "derive", "generated", "generate", "produced", "produce", "computed", "compute",
    "calculated", "calculate", "calculation", "observed", "observation", "observations", "actual", "measured", "measure",
    "measures", "measurement", "record", "records", "recorded", "statement", "statements", "triple", "triples", "rdf",
    "sparql", "owl", "shacl", "turtle", "ttl", "ontology", "ontologies", "class", "classes", "property", "properties",
    "vocabulary", "term", "terms", "schema", "knowledge graph", "knowledge graphs", "kg", "graph", "graphs", "entity",
    "entities", "resource", "resources", "node", "nodes", "uri", "iri", "licence", "license", "licensed", "publisher",
    "publishers", "published", "metadata", "inventory", "loaded", "available", "hold", "holds", "contain", "contains",
    "cover", "covers", "coverage", "scope", "support", "supports", "supported", "notebook", "stage", "stages", "paper",
    "section", "sections", "figure", "figures", "method", "methods", "methodology", "approach", "approaches", "how was",
    "how is", "how were", "how are", "trust", "trustworthy", "verify", "verified", "verifiable", "traceable", "traceability",
    "hallucination", "hallucinate", "cleets", "cleets-kg", "cleets-kg-enriched", "cskg", "enriched", "prediction kg",
    "version", "release", "released", "updated", "update", "last updated", "wimd", "statswales", "stats wales", "dft",
    "dvla", "ons", "ozev", "department for transport", "office for national statistics", "welsh government",
    "cardiff university", "open government licence", "ogl", "cc by", "creative commons", "nomis",
    "define", "defined", "defines", "definition", "definitions", "type", "types", "kind", "kinds", "family", "families",
    "organisation", "organization", "agency", "institution", "author", "authors", "authored", "creator", "created",
    "create", "maintainer", "maintained", "maintains", "information", "info", "fact", "facts", "statistic", "statistics",
    "stats", "built", "build", "constructed", "integrated", "integration", "integrates", "linked", "link", "links",
    "connected", "connection", "aligned", "alignment", "reuse", "reused", "conform", "conforms", "quality", "complete",
    "completeness", "missing", "cited sources",
)

# Table and dataset-builder requests (qa.TABLE_TRIGGERS is merged in at run time as well).
TABLE_WORDS = ("table", "tables", "csv", "download", "downloadable", "extract", "export", "spreadsheet", "tabulate",
               "give me the data", "list the", "pull", "column", "columns", "row", "rows", "custom dataset", "builder")

# Generic geography words: they anchor a question to the modelled districts without naming one.
PLACE_WORDS = ("wales", "welsh", "lad", "lads", "local authority", "local authorities", "district", "districts",
               "area", "areas", "region", "regions", "regional", "council", "councils", "county", "counties", "authority",
               "authorities", "nation", "nationwide", "national", "country", "countrywide", "place", "places",
               "everywhere", "all lads", "every lad", "each lad", "borough", "boroughs", "city", "cities", "town", "towns",
               "municipality", "municipalities", "locality", "localities", "the valleys", "valleys", "north wales",
               "south wales", "mid wales", "west wales")

# Words that carry no subject of their own: question words, auxiliaries, comparison and analysis vocabulary.
STOP_WORDS = set("""
a an the and or but nor so yet of in on at to for from by with without within into onto over under about above below
between among across through during before after since until till than as is are was were be been being am do does did
done doing have has had having will would shall should can could may might must need needs needed dare ought let lets
i me my mine we us our ours you your yours he him his she her hers it its they them their theirs this that these those
there here where when why how what which who whom whose whether if then else because while although though even
unless whereas wherever whenever whatever whichever whoever not no non never none nothing nobody nowhere neither either
any some all both each every few many much more most other another such own same very too also just only still already
again further ever often always usually sometimes seldom rarely now today currently presently recently lately soon
once twice first second third last next previous prior final finally
please thanks thank kindly hello hi hey ok okay yes yeah yep nope right sure
tell show give get find list describe summarise summarize summary overview outline detail details
know knows knew known think thought believe guess wonder wondering want wants wanted like likes
say says said mean means meant look looks looking see seen sees check checks compare compares compared comparison
comparing differ differs different difference differences similar similarity similarities versus vs against
unlike rank ranks ranked ranking rankings order ordered sort sorted top bottom highest lowest higher lower high low
central best worst better worse biggest smallest largest least most greatest fewer fewest less max min maximum minimum
average median total totals sum overall general generally typical typically normally usual
number numbers count counts figure figures value values amount amounts quantity level levels rate rates proportion
proportions percentage percent per cent pct share shares size sizes big large small long short wide narrow great little
change changed changes changing trend trends pattern patterns distribution variation vary varies varied growth grow
grows growing grown increase increased increases increasing rise rises risen rising decline declined declines
declining fall falls fell fallen drop drops dropped decrease decreased decreases decreasing gap gaps spread range
over time series history historical historic past current recent newest oldest present
year years quarter quarters month months week weeks day days annual annually quarterly monthly yearly decade decades
how many how much how often how far how long how big
sq km kilometre kilometres kilometer kilometers square
can you could you would you will you do you did you are you is there are there was there were there
regarding concerning question questions ask asked asking answer answers answered reply
really quite rather fairly pretty somewhat relatively roughly approximately around nearly almost exactly
together combined whole entire individual individually single
good bad nice fine well badly
make makes made making come comes came go goes went gone take takes took taken put puts set sets run runs
ran running keep keeps kept hold holds held stay stays stayed remain remains remained become becomes became
one two three four five six seven eight nine ten hundred thousand million billion half double triple
up down out off away back forward along
etc eg ie
demand supply installed install installation deployed deployment rollout provide provided provides required
requires require requirement requirements plan plans planned planning likely unlikely probably possible possibly
new old newer older newest existing additional extra current working functional operational active aggregate aggregated
cumulative net gross strong strongly weak weakly robust significant significantly notable notably steady steadily sharp
sharply rapid rapidly gradual gradually considerable considerably substantial substantially modest marginal dramatic
dramatically remarkable striking surprising interesting important main major minor key primary principal relative
absolute real true correct exact precise rough detailed full partial limited broad specific particular certain obvious
clear simple basic quick brief properly correctly fully completely appropriately adequately entirely wholly
use used uses using usage
""".split())

# Topics stakeholders ask about that no dataset in the graphs records. Phrases are matched longest-first, after
# the modelled vocabulary, so "charging station" is a charger question but "station" alone is a geography one.
UNMODELLED_TOPICS: List[Tuple[str, Tuple[str, ...], str]] = [
    ("Prices, costs and incentives",
     ("price", "prices", "priced", "pricing", "cost", "costs", "costly", "cheap", "cheaper", "cheapest", "expensive",
      "afford", "affordable", "affordability", "grant", "grants", "subsidy", "subsidies", "subsidised", "subsidized",
      "incentive", "incentives", "rebate", "rebates", "tax", "taxes", "taxed", "taxation", "vat", "tariff", "tariffs",
      "fee", "fees", "pay", "pays", "paid", "payment", "payments", "budget", "budgets", "money", "revenue", "revenues",
      "profit", "profits", "road tax", "vehicle excise duty", "ved", "loan", "loans", "finance", "financing", "lease",
      "leasing", "insurance", "salary sacrifice"),
     "No dataset in the graphs records prices, costs, incentives or spending; the sources are counts of vehicles and "
     "charging devices, population, density and income deprivation."),
    ("Charger speeds, home charging, electricity and the grid",
     ("electricity", "grid", "kwh", "kw", "megawatt", "megawatts", "mw", "power rating", "power ratings", "charging speed",
      "charging speeds", "rapid charger", "rapid chargers", "rapid charging", "ultra-rapid", "ultra rapid", "fast charger",
      "fast chargers", "fast charging", "slow charger", "slow chargers", "slow charging", "wattage", "voltage", "energy",
      "energy demand", "battery capacity", "battery size", "battery range", "driving range", "range anxiety", "mileage",
      "miles per", "consumption", "solar", "renewable", "renewables", "home charging", "home charger", "home chargers",
      "workplace charging", "driveway", "driveways", "off-street", "on-street", "lamp post", "lamppost", "connector",
      "connectors", "plug", "plugs", "socket", "sockets", "ccs", "chademo", "type 2", "utilisation", "utilization",
      "occupancy", "uptime", "downtime", "broken chargers", "out of order"),
     "EVCI9001 enters the graph only as counts of public charging devices per district; charger speeds and power "
     "ratings, home or workplace charging, utilisation, electricity demand and grid capacity are not modelled."),
    ("Emissions and air quality",
     ("emission", "emissions", "co2", "carbon", "carbon dioxide", "greenhouse", "greenhouse gas", "ghg", "pollution",
      "polluting", "pollutant", "pollutants", "air quality", "nox", "particulate", "particulates", "pm2.5", "pm10",
      "net zero", "net-zero", "decarbonisation", "decarbonization", "decarbonise", "decarbonize", "footprint",
      "climate change", "global warming", "environmental", "environment"),
     "Emissions, air quality and carbon savings are not modelled: the graphs hold vehicle and charging-device counts, "
     "not their environmental effects."),
    ("Fuel types other than battery-electric",
     ("petrol", "gasoline", "diesel", "hybrid", "hybrids", "phev", "phevs", "plug-in hybrid", "plug-in hybrids",
      "plugin hybrid", "hydrogen", "fuel cell", "fuel cells", "lpg", "cng", "biofuel", "biofuels", "internal combustion",
      "combustion", "fuel", "fuels", "fossil"),
     "The graphs hold private battery-electric keepership (VEH0132) and the total private vehicle stock (VEH0105); "
     "petrol, diesel, hybrid and hydrogen vehicles are not held separately and appear only as the non-BEV remainder "
     "(and as the residual non-BEV stock of the turnover scenario)."),
    ("Transport modes and fleets other than privately kept vehicles",
     ("bus", "buses", "coach", "coaches", "train", "trains", "rail", "railway", "railways", "tram", "trams", "metro",
      "taxi", "taxis", "cab", "cabs", "uber", "e-scooter", "e-scooters", "scooter", "scooters", "bike", "bikes",
      "e-bike", "e-bikes", "ebike", "ebikes", "bicycle", "bicycles", "cycling", "cyclist", "cyclists", "motorbike",
      "motorbikes", "motorcycle", "motorcycles", "lorry", "lorries", "hgv", "hgvs", "truck", "trucks", "freight",
      "haulage", "company car", "company cars", "company fleet", "company fleets", "company-kept", "business fleet",
      "business fleets", "fleet operator", "fleet operators", "car club", "car clubs", "car sharing", "ride hailing",
      "public transport", "aviation", "flights", "ferry", "ferries", "shipping"),
     "Only privately kept road vehicles are modelled (the private keepership extracts of VEH0132 and VEH0105); "
     "buses, rail, taxis, two-wheelers, HGVs and company-kept fleets are outside the graphs."),
    ("Locations finer than a local authority district",
     ("postcode", "postcodes", "street", "streets", "car park", "car parks", "parking", "station", "stations",
      "service station", "service stations", "motorway", "motorways", "ward", "wards", "lsoa", "lsoas", "msoa", "msoas",
      "output area", "output areas", "neighbourhood", "neighbourhoods", "neighborhood", "neighborhoods", "village",
      "villages", "suburb", "suburbs", "constituency", "constituencies", "supermarket", "supermarkets",
      "shopping centre", "shopping centres", "retail park", "address", "addresses", "location", "locations", "site",
      "sites", "where exactly", "nearest", "near me", "nearby", "map of chargers", "coordinates"),
     "The finest geography in the graphs is the local authority district: observations are district totals, so "
     "streets, postcodes, wards, car parks and individual charging sites are not modelled."),
    ("Distances, journeys and traffic",
     ("distance", "distances", "how far", "miles", "mile", "journey", "journeys", "route", "routes", "routing", "travel",
      "travels", "travelling", "traveling", "trip", "trips", "commute", "commuting", "commuters", "traffic", "congestion",
      "road network", "roads", "road", "speed limit", "accident", "accidents", "collision", "collisions", "casualties"),
     "Distances, journeys, routes and traffic are not modelled; the graphs describe districts, not movements between them."),
    ("Demographic, economic and social variables beyond population, density and income deprivation",
     ("gender", "sex", "ethnicity", "ethnic", "employment", "unemployment", "employed", "unemployed", "job", "jobs",
      "wage", "wages", "salary", "salaries", "earnings", "gdp", "gva", "house price", "house prices", "housing",
      "homes", "households", "household", "rent", "rents", "rental", "mortgage", "education", "school", "schools",
      "students", "health", "hospital", "hospitals", "nhs", "crime", "crimes", "births", "deaths", "mortality",
      "migration", "immigration", "life expectancy", "disability", "disabled", "elderly", "pensioners", "retired",
      "retirement", "age profile", "average age", "median age", "age group", "age groups", "young people", "children"),
     "Beyond resident population, population density and income deprivation (WIMD 2025 income domain), no demographic, "
     "labour-market, housing, health or crime variables are in the graphs."),
    ("Weather, climate and floods",
     ("weather", "weather forecast", "temperature", "temperatures", "rain", "rains", "rainfall", "raining", "snow",
      "snowing", "wind", "winds", "windy", "storm", "storms", "flood", "floods", "flooding", "heatwave", "heatwaves",
      "sunshine", "sunny", "cloudy", "humidity", "climate", "frost", "drought", "sea level"),
     "Weather, climate and flood variables are not in the graphs."),
    ("Vehicle makes and models",
     ("tesla", "teslas", "nissan", "nissan leaf", "leaf", "model 3", "model y", "model s", "model x", "byd", "kia",
      "hyundai", "vauxhall", "renault", "bmw", "mercedes", "audi", "volkswagen", "vw", "polestar", "toyota", "ford",
      "peugeot", "citroen", "skoda", "volvo", "jaguar", "fiat", "honda", "mazda", "cupra", "porsche", "lexus", "dacia",
      "brand", "brands", "manufacturer", "manufacturers", "marque", "marques", "makes of car", "make of car", "buy",
      "buying", "bought", "purchase", "purchased", "purchasing", "recommend", "recommended", "recommendation",
      "second-hand", "second hand", "used cars", "used car", "new cars", "new car", "sales", "sold", "dealership",
      "dealerships", "dealer", "dealers"),
     "Vehicle makes, models and sales are not in the graphs: VEH0132 is used as district totals of privately kept "
     "battery-electric vehicles."),
    ("People, organisations and political roles",
     ("mayor", "mayors", "minister", "ministers", "prime minister", "first minister", "councillor", "councillors",
      "mp", "mps", "member of parliament", "senedd member", "president", "ceo", "politician", "politicians",
      "political party", "labour party", "conservative party", "plaid cymru", "liberal democrats", "election",
      "elections", "elected", "vote", "votes", "voted", "voters", "manifesto", "manifestos", "campaign", "campaigns"),
     "People, organisations and political roles are not modelled, apart from the dataset publishers recorded in each "
     "dataset record."),
]

# Places outside the modelled geography that stakeholders name. "England" is described from the graph itself
# (English districts are held with population density only).
OUTSIDE_PLACES = (
    "uk", "united kingdom", "britain", "great britain", "british", "gb", "scotland", "scottish", "northern ireland",
    "ireland", "irish", "london", "greater london", "europe", "european", "european union", "eu", "usa", "united states",
    "america", "american", "france", "french", "paris", "germany", "german", "berlin", "spain", "spanish", "italy",
    "italian", "norway", "norwegian", "netherlands", "dutch", "sweden", "denmark", "china", "chinese", "india", "indian",
    "japan", "japanese", "australia", "australian", "canada", "canadian", "abroad", "overseas", "rest of the uk",
    "england", "english",
)

GREETINGS = ("hello", "hi", "hey", "hiya", "good", "morning", "afternoon", "evening", "thanks", "thank", "you",
             "cheers", "ok", "okay", "test", "testing", "yo")
META_PHRASES = ("what can you do", "what can i ask", "what do you do", "how does this work", "how do you work",
                "how does it work", "who are you", "what are you", "what is cleets-chat", "what is cleets chat",
                "help me", "instructions", "how to use", "how do i use", "what is this tool", "what is this chatbot",
                "what is this site", "what is this app", "are you an ai", "are you chatgpt", "are you a bot",
                "what is your name", "can you help")

# --------------------------------------------------------------------------- text normalisation
_TOKEN_RE = re.compile(r"[a-z0-9£$€%]+")
_YEAR_RE = re.compile(r"\b(1[89]\d\d|20\d\d|21\d\d)\b")
_SUFFIXES = ("ations", "ation", "ingly", "ings", "ing", "ions", "ion", "ies", "ied", "ers", "est", "ly", "ed", "es", "er", "s")


def normalise(text: str) -> str:
    t = (text or "").casefold()
    t = t.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    t = re.sub(r"'s\b", "", t)  # Cardiff's -> cardiff
    return t


def stem(word: str) -> str:
    """Light, deterministic suffix stripping applied identically to the vocabulary and the question, so that
    morphological variants match (charger / charging / charged -> charg; slowest / slowly -> slow)."""
    w = word
    if len(w) <= 3 or any(ch.isdigit() for ch in w):
        return w
    for _ in range(3):
        changed = False
        for suf in _SUFFIXES:
            if w.endswith(suf) and len(w) - len(suf) >= 3:
                w = w[:-len(suf)] + ("y" if suf in ("ies", "ied") else "")
                changed = True
                break
        if not changed:
            break
    if w.endswith("e") and len(w) > 4:
        w = w[:-1]
    return w


def tokens(text: str) -> List[str]:
    return _TOKEN_RE.findall(normalise(text))


def _phrase(p: str) -> Tuple[str, ...]:
    return tuple(stem(t) for t in _TOKEN_RE.findall(normalise(p)))


# --------------------------------------------------------------------------- vocabulary (built once per KG)
STRONG = {"measure", "prediction", "accuracy"}   # the question has a modelled subject
WEAK = {"place", "provenance", "table"}           # the question points at the graph but names no subject


class Vocabulary:
    """Stemmed phrase -> category index built from the graphs plus the routing lexicons."""

    def __init__(self, kg):
        self.kg = kg
        self.phrases: Dict[Tuple[str, ...], str] = {}    # stemmed phrase -> category
        self.topic_of: Dict[Tuple[str, ...], int] = {}   # stemmed phrase -> UNMODELLED_TOPICS index
        self.measure_of: Dict[Tuple[str, ...], str] = {}  # stemmed phrase -> measure label it stands for
        self.max_len = 1
        self._build()

    def _add(self, phrase: str, category: str, topic: Optional[int] = None, measure: Optional[str] = None):
        key = _phrase(phrase)
        if not key or key in self.phrases:   # first category wins: modelled vocabulary is added first
            return
        self.phrases[key] = category
        if topic is not None:
            self.topic_of[key] = topic
        if measure is not None:
            self.measure_of[key] = MEASURE_LABELS.get(measure, measure)
        self.max_len = max(self.max_len, len(key))

    def measure_label(self, surface: str) -> Optional[str]:
        return self.measure_of.get(_phrase(surface))

    def _build(self):
        kg = self.kg
        try:
            from qa_with_humanization import COLUMN_KEYWORDS, FAMILY_KEYWORDS, ACCURACY_KEYWORDS, TABLE_TRIGGERS, TABLE_WEAK
        except Exception:  # pragma: no cover
            COLUMN_KEYWORDS, FAMILY_KEYWORDS, ACCURACY_KEYWORDS, TABLE_TRIGGERS, TABLE_WEAK = [], [], (), (), ()
        # 1. districts (names, codes, aliases) and generic geography
        for alias in getattr(kg, "_alias", {}):
            self._add(alias, "place")
        for w in PLACE_WORDS:
            self._add(w, "place")
        # 2. measures: graph labels, routing keywords, synonyms
        try:
            labels = list(kg.actual_inventory().get("measures", []))
        except Exception:
            labels = []
        for label in labels + list(MEASURE_LABELS.values()):
            self._add(label, "measure", measure=label)
            for part in re.split(r"[(),/]", label):
                if len(part.split()) >= 2:
                    self._add(part, "measure", measure=label)
        for lexicon in (MEASURE_KEYWORDS, MEASURE_SYNONYMS, COLUMN_KEYWORDS):
            for key, words in lexicon:
                if key not in MEASURE_LABELS:   # prediction columns of the dataset builder are added below
                    continue
                for w in words:
                    self._add(w, "measure", measure=key)
        # 3. predictions: family labels from the graph, routing keywords, generic words
        try:
            for f in kg.prediction_families():
                self._add(f["label"], "prediction")
                for part in re.split(r"[(),/]", f["label"]):
                    if len(part.split()) >= 2:
                        self._add(part, "prediction")
        except Exception:
            pass
        for lexicon in (FAMILY_KEYWORDS, COLUMN_KEYWORDS):
            for key, words in lexicon:
                if lexicon is COLUMN_KEYWORDS and key in MEASURE_LABELS:
                    continue
                for w in words:
                    self._add(w, "prediction")
        for w in FAMILY_WORDS + PREDICTION_WORDS:
            self._add(w, "prediction")
        for w in tuple(ACCURACY_KEYWORDS) + ACCURACY_WORDS:
            self._add(w, "accuracy")
        # 4. provenance: dataset identifiers and publishers, ontology terms, generic words
        for d, entry in getattr(kg, "_datasets", {}).items():
            self._add(entry[0], "provenance")
            meta = getattr(kg, "_dataset_meta", {}).get(str(d), {})
            for part in re.split(r"[/(),]", meta.get("publisher", "")):
                if part.strip():
                    self._add(part, "provenance")
        try:
            for t in kg.ontology_terms():
                key = _phrase(t["label"])
                cat = "measure" if any(self.phrases.get((s,)) == "measure" for s in key) else "provenance"
                self._add(t["label"], cat)
        except Exception:
            pass
        for w in PROVENANCE_WORDS:
            self._add(w, "provenance")
        for w in tuple(TABLE_TRIGGERS) + tuple(TABLE_WEAK) + TABLE_WORDS:
            self._add(w, "table")
        # 5. curated unmodelled topics and outside places (never override modelled vocabulary)
        for i, (_, words, _) in enumerate(UNMODELLED_TOPICS):
            for w in words:
                self._add(w, "unmodelled", topic=i)
        for w in OUTSIDE_PLACES:
            self._add(w, "outside")
        # 6. stop words
        for w in STOP_WORDS:
            self._add(w, "neutral")

    def tag(self, words: List[str]) -> List[Tuple[str, str, Optional[int]]]:
        """Greedy longest-match tagging of a token list: [(surface, category, topic index or None), ...]."""
        stems = [stem(w) for w in words]
        out: List[Tuple[str, str, Optional[int]]] = []
        i = 0
        while i < len(stems):
            matched = False
            for n in range(min(self.max_len, len(stems) - i), 0, -1):
                key = tuple(stems[i:i + n])
                cat = self.phrases.get(key)
                if cat is not None:
                    out.append((" ".join(words[i:i + n]), cat, self.topic_of.get(key)))
                    i += n
                    matched = True
                    break
            if not matched:
                w = words[i]
                cat = "neutral" if (any(ch.isdigit() for ch in w) or len(w) <= 1) else "unknown"
                out.append((w, cat, None))
                i += 1
        return out


_VOCAB_CACHE: Dict[int, Vocabulary] = {}


def vocabulary(kg) -> Vocabulary:
    v = _VOCAB_CACHE.get(id(kg))
    if v is None or v.kg is not kg:
        v = Vocabulary(kg)
        _VOCAB_CACHE.clear()
        _VOCAB_CACHE[id(kg)] = v
    return v


# --------------------------------------------------------------------------- coverage (read from the graphs)
def coverage(kg) -> dict:
    """What the loaded graphs cover, for the reason text: districts, measures, years, prediction types, horizon."""
    try:
        inv = kg.actual_inventory()
    except Exception:
        inv = {"measures": [], "lads": []}
    try:
        pinv = kg.prediction_inventory()
    except Exception:
        pinv = {"years": (None, None), "prediction_count": 0}
    try:
        fams = kg.prediction_families()
    except Exception:
        fams = []
    obs_years = kg.observation_years() if hasattr(kg, "observation_years") else (None, None)
    try:
        n_obs = sum(len(kg.observations(n)) for n in kg.lad_names())
    except Exception:
        n_obs = 0
    turnover = bool(kg.turnover_rows()) if hasattr(kg, "turnover_rows") else False
    return {
        "lads": list(inv.get("lads") or kg.lad_names()),
        "measures": list(inv.get("measures", [])),
        "obs_years": tuple(obs_years),
        "n_obs": n_obs,
        "pred_years": tuple(pinv.get("years") or (None, None)),
        "n_pred": pinv.get("prediction_count", 0),
        "families": [f["label"] for f in fams],
        "turnover_end": 2053 if turnover else None,
        "other_areas": len(kg.other_areas()) if hasattr(kg, "other_areas") else 0,
    }


def coverage_sentence(cov: dict) -> str:
    measures = ", ".join(cov["measures"]) if cov["measures"] else "the observed measures"
    y0, y1 = cov["obs_years"]
    span = f", {y0} to {y1}" if y0 and y1 else ""
    p0, p1 = cov["pred_years"]
    horizon = f" ({p0} to {p1}" if p0 and p1 else " ("
    if cov["turnover_end"]:
        horizon += f"; fleet turnover to {cov['turnover_end']}"
    horizon += ")"
    return (f"The graphs model {len(cov['lads'])} Welsh local authority districts with {cov['n_obs']:,} observations of "
            f"{len(cov['measures'])} measures ({measures}){span}, and the companion paper's {len(cov['families'])} "
            f"prediction types{horizon}. Answers are composed only from these statements, so a question outside them is "
            f"declined rather than guessed.")


# --------------------------------------------------------------------------- the check
HINT = ("*If the question is about the modelled data but worded differently, use the wording of the help panel: "
        "retrieval is keyword-based and does not infer meaning.*")


def _years_in(text: str) -> List[int]:
    return [int(y) for y in _YEAR_RE.findall(normalise(text))]


def _examples(kg, mode: str, lad: Optional[str] = None) -> List[str]:
    names = kg.lad_names() if hasattr(kg, "lad_names") else []
    lad = lad or ("Cardiff" if "Cardiff" in names else (names[0] if names else "Cardiff"))
    if mode == "prediction":
        return [f"What is {lad}'s predicted EV keepership in 2045 under the central scenario?", "Which LADs diffuse most slowly?"]
    return [f"What do you know about {lad}?", "Which LAD has the most public EV chargers?"]


def _finish(kg, mode: str, headline: str, reason: str, verdict: str, unmodelled: List[str], modelled: List[str],
            lad: Optional[str] = None, extra: str = "") -> dict:
    lines = ["### Not modelled in the knowledge graph", "", f"{headline} {reason}".strip(), "", coverage_sentence(coverage(kg))]
    if extra:
        lines += ["", extra]
    if modelled:
        lines += ["", "**Modelled in your question:** " + "; ".join(modelled) + "."]
    lines += ["", "**Try instead:** " + " · ".join(f"*{q}*" for q in _examples(kg, mode, lad)) + " (the ⓘ button lists more).",
              "", f"**Knowledge graph:** [CLEETS]({ONTOLOGY_URL})"]
    return {"markdown": "\n".join(lines), "kind": "scope", "family": None, "table": None, "columns": None,
            "scope": {"verdict": verdict, "unmodelled": unmodelled, "modelled": modelled}}


def _quote(terms: List[str]) -> str:
    return ", ".join(f"'{t}'" for t in terms[:4])


def _original(question: str, surface: str) -> str:
    """The term as the user typed it (casing kept), for quoting back; `surface` is the normalised token string."""
    pattern = r"\b" + r"\W+".join(re.escape(t) for t in surface.split()) + r"\b"
    m = re.search(pattern, question, re.IGNORECASE)
    return m.group(0) if m else surface


def _verb(terms: List[str]) -> str:
    return "is" if len(terms) == 1 else "are"


def meta_answer(kg, question: str, mode: str) -> Optional[dict]:
    """Greetings and questions about the assistant itself: a short description instead of a retrieval."""
    q = normalise(question).strip(" ?!.,")
    words = tokens(q)
    is_greeting = bool(words) and len(words) <= 3 and all(w in GREETINGS for w in words)
    is_meta = any(p in q for p in META_PHRASES) and not any(
        w in q for w in ("keepership", "charger", "charging", "population", "deprivation", "predict", "forecast", "lad",
                         "district", "ontology", "dataset", "table"))
    if not (is_greeting or is_meta):
        return None
    md = ("### CLEETS-CHAT answers from the knowledge graphs only\n\n"
          "It has no conversational model: every answer is assembled from retrieved statements of CLEETS-KG-Enriched "
          "and the CLEETS Prediction KG, with the dataset behind each value, and a question outside the graphs is "
          "declined with the reason.\n\n" + coverage_sentence(coverage(kg)) + "\n\n**Try:** "
          + " · ".join(f"*{x}*" for x in _examples(kg, mode)) + " (the ⓘ button lists more).\n\n"
          f"**Knowledge graph:** [CLEETS]({ONTOLOGY_URL})")
    return {"markdown": md, "kind": "meta", "family": None, "table": None, "columns": None,
            "scope": {"verdict": "meta", "unmodelled": [], "modelled": []}}


def _detect_family(question: str) -> str:
    try:
        from qa_with_humanization import detect_family
        return detect_family(question)
    except Exception:  # pragma: no cover
        return "diffusion"


def check_scope(kg, question: str, mode: str = "actual", family: Optional[str] = None) -> Optional[dict]:
    """Return a 'not modelled' answer dict when the question lies outside the loaded graphs, else None."""
    if not question or not question.strip():
        return None
    meta = meta_answer(kg, question, mode)
    if meta is not None:
        return meta
    vocab = vocabulary(kg)
    tagged = vocab.tag(tokens(question))

    lads = kg.find_lads_in_text(question) if hasattr(kg, "find_lads_in_text") else []
    others = kg.find_other_areas_in_text(question) if hasattr(kg, "find_other_areas_in_text") else []
    cats = {c for _, c, _ in tagged}
    if lads:
        cats.add("place")
    typed = lambda ws: list(dict.fromkeys(_original(question, w) for w in ws))  # noqa: E731  (quote terms as typed)
    unknown = typed(w for w, c, _ in tagged if c == "unknown")
    # an unrecognised word directly qualifying a measure names a different quantity ("dog ownership", "home ownership")
    compounds = [(_original(question, f"{tagged[i][0]} {tagged[i + 1][0]}"), vocab.measure_label(tagged[i + 1][0]) or tagged[i + 1][0])
                 for i in range(len(tagged) - 1) if tagged[i][1] == "unknown" and tagged[i + 1][1] == "measure"]
    topics = list(dict.fromkeys(t for _, c, t in tagged if c == "unmodelled" and t is not None))
    topic_terms = typed(w for w, c, _ in tagged if c == "unmodelled")
    outside_tokens = list(dict.fromkeys(w for w, c, _ in tagged if c == "outside"))
    outside = typed(outside_tokens)
    strong = bool(cats & STRONG)
    weak = bool(cats & WEAK)
    lad_name = lads[0][0] if lads else None

    modelled: List[str] = [f"{name} (Welsh local authority district)" for name, _ in lads]
    seen = set()
    for w, c, _ in tagged:
        if c in STRONG and w not in seen and not any(ch.isdigit() for ch in w):
            seen.add(w)
            modelled.append(f"{w} ({'measure' if c == 'measure' else 'prediction vocabulary'})")
    modelled = modelled[:4]

    # 1. curated unmodelled topics: the reason names the dataset that would have been needed
    if topics:
        title, _, reason = UNMODELLED_TOPICS[topics[0]]
        head = f"{title} ({_quote(topic_terms)}) are not modelled."
        return _finish(kg, mode, head, reason, "topic", topic_terms, modelled, lad_name)

    # 2. places outside the modelled geography (English districts are described from the graph itself)
    if others:
        name, info = others[0]
        shown = info.get("matched") or name
        held = ", ".join(info.get("measures") or []) or "no observations"
        years = f" for {info['first']} to {info['last']}" if info.get("first") and info.get("last") else ""
        head = (f"'{shown}' is in the graph as an {info.get('kind', 'English local authority district')}"
                + (f" ({name})" if shown.casefold() != name.casefold() else "") + f" with {held}{years} only.")
        reason = ("EV keepership, public charging, income deprivation and all predictions are modelled for the 22 Welsh "
                  "districts, so the question cannot be answered for it from the graphs.")
        return _finish(kg, mode, head, reason, "geography", [name], modelled, lad_name)
    if outside:
        if outside_tokens[0] in ("england", "english"):
            head = "'England' is outside the modelled scope."
            reason = (f"The graph holds the {coverage(kg)['other_areas']} English districts with population density only "
                      "(ONSDensity); EV keepership, public charging, income deprivation and all predictions are modelled "
                      "for the 22 Welsh districts.")
        else:
            head = f"{_quote(outside)} {_verb(outside)} outside the modelled geography."
            reason = ("The graphs cover the 22 Welsh local authority districts (plus English districts with population "
                      "density only); no other country, region or city is in them.")
        return _finish(kg, mode, head, reason, "geography", outside, modelled, lad_name)

    # 3. temporal scope
    cov = coverage(kg)
    years = _years_in(question)
    y0, y1 = cov["obs_years"]
    p0, p1 = cov["pred_years"]
    if years and y0 and y1:
        if mode == "prediction" or "prediction" in cats or "table" in cats:
            detected = family or _detect_family(question)
            horizon = cov["turnover_end"] if (detected == "turnover" and cov["turnover_end"]) else (p1 or y1)
            earliest = min(y0, p0 or y0)
        else:
            horizon, earliest = y1, y0
        bad = [y for y in years if y < earliest or y > horizon]
        if bad:
            yb = bad[0]
            if yb < earliest:
                head = f"'{yb}' predates the graphs."
                reason = f"The earliest observation is from {y0}; nothing before it is recorded."
            elif mode == "actual" and p0 and p1 and p0 <= yb <= (cov["turnover_end"] or p1):
                head = f"'{yb}' is beyond the observed data."
                reason = (f"Observations run from {y0} to {y1}; {yb} is covered only by the predictions, so switch to "
                          f"Prediction mode to ask about it.")
            else:
                head = f"'{yb}' is beyond the prediction horizon."
                reason = (f"Forecasts run to {p1} Q4" + (f" and the fleet-turnover scenario to {cov['turnover_end']} Q4"
                                                        if cov["turnover_end"] else "") + "; nothing after that is modelled.")
            return _finish(kg, mode, head, reason, "temporal", [str(yb)], modelled, lad_name)

    # 4. nothing modelled in the question at all
    if not strong and not weak:
        if unknown:
            head = f"{_quote(unknown)} {_verb(unknown)} not modelled."
            reason = ("Nothing in the question corresponds to a district, measure, prediction type, dataset or ontology "
                      "term in the loaded graphs.")
        else:
            head = "The question names nothing that is modelled."
            reason = "It contains no district, measure, prediction type, dataset or ontology term held in the loaded graphs."
        return _finish(kg, mode, head, reason, "unmodelled", unknown, modelled, lad_name, extra=HINT)

    # 5. a measure qualified by an unrecognised word is a different quantity ("dog ownership" is not keepership)
    if compounds:
        terms = [c for c, _ in compounds]
        nearest = ", ".join(dict.fromkeys(label for _, label in compounds))
        head = f"{_quote(terms)} {_verb(terms)} not modelled."
        reason = (f"No observation or dataset in the graphs describes {_quote(terms)}; the nearest measure held is "
                  f"{nearest}, as listed below.")
        return _finish(kg, mode, head, reason, "partial", terms, modelled, lad_name, extra=HINT)

    # 6. a district, table or provenance request whose subject is not modelled
    if not strong and unknown:
        placed = bool(lad_name) or "place" in cats
        where = lad_name or "Wales"
        head = f"{_quote(unknown)} {_verb(unknown)} not modelled{' for ' + where if placed else ''}."
        reason = ((f"{where} is in the graph, but no" if placed else "No")
                  + f" observation, prediction or dataset describes {_quote(unknown)}; the graphs hold only the measures "
                    "and prediction types listed below.")
        return _finish(kg, mode, head, reason, "partial", unknown, modelled, lad_name, extra=HINT)

    return None
