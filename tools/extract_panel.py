"""Extract the quarterly district panel from CLEETS-KG (v1.3.0 vocabulary).

One row per Welsh local authority district and quarter. Columns:
  lad_code, lad_name, year, quarter, period,
  ev_keepership        private battery-electric keepership (VEH0132)
  ev_chargers          public charging devices (EVCI9001), from 2019-Q4
  private_stock        licensed private vehicles, all body types, all fuels (VEH0105)
  adoption_share       ev_keepership / private_stock
  evs_per_1000         derived in the graph
  chargers_per_100k    derived in the graph
  keepers_per_charger  derived in the graph (AdoptionRatioObservation)
  population           mid-year population for the observation year (StatsWales)
  density              persons per sq km for the observation year (ONS)
  income_deprivation_decile  mean WIMD 2025 income-domain decile (1 = most deprived)
"""
import sys
import pandas as pd
from rdflib import Graph

src = sys.argv[1] if len(sys.argv) > 1 else "data/cleets_cskg_enriched.ttl"
out = sys.argv[2] if len(sys.argv) > 2 else "data/cleets_lad_quarter_panel.csv"

g = Graph()
g.parse(src, format="turtle")
print(f"Graph loaded: {len(g):,} triples")

PREFIX = """
PREFIX cleets: <https://w3id.org/def/cleets#>
PREFIX rdf:    <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs:   <http://www.w3.org/2000/01/rdf-schema#>
PREFIX dcterms:<http://purl.org/dc/terms/>
PREFIX cleetsdata: <https://w3id.org/def/cleets/data#>
"""

def q(sparql):
    return pd.DataFrame([{str(k): (v.toPython() if v is not None else None) for k, v in r.asdict().items()}
                         for r in g.query(PREFIX + sparql)])

lads = q("""
SELECT ?lad ?code ?name WHERE {
  ?lad rdf:type cleets:WelshLAD ; cleets:ladCode ?code ; rdfs:label ?name . }""")
lads["name"] = lads["name"].str.strip()

keep = q("""
SELECT ?code ?year ?quarter ?value WHERE {
  ?o rdf:type cleets:EVKeepership ; cleets:forLAD ?lad ; cleets:forTime ?t ; cleets:keepershipValue ?value .
  ?lad rdf:type cleets:WelshLAD ; cleets:ladCode ?code .
  ?t cleets:year ?year ; cleets:quarter ?quarter . }""").rename(columns={"value": "ev_keepership"})

chg = q("""
SELECT ?code ?year ?quarter ?value WHERE {
  ?o rdf:type cleets:EVChargerCount ; cleets:forLAD ?lad ; cleets:forTime ?t ; cleets:chargerCountValue ?value .
  ?lad rdf:type cleets:WelshLAD ; cleets:ladCode ?code .
  ?t cleets:year ?year ; cleets:quarter ?quarter . }""").rename(columns={"value": "ev_chargers"})

def generic(prop, col):
    return q(f"""
SELECT ?code ?year ?quarter ?value WHERE {{
  ?o rdf:type cleets:Observation ; cleets:observesProperty cleetsdata:{prop} ;
     cleets:forLAD ?lad ; cleets:forTime ?t ; cleets:hasSimpleResult ?value .
  ?lad rdf:type cleets:WelshLAD ; cleets:ladCode ?code .
  ?t cleets:year ?year ; cleets:quarter ?quarter . }}""").rename(columns={"value": col})

stock = generic("PrivateVehicleStockProperty", "private_stock")
per1000 = generic("EVsPerThousandResidentsProperty", "evs_per_1000")
per100k = generic("ChargersPer100kResidentsProperty", "chargers_per_100k")

ratio = q("""
SELECT ?code ?year ?quarter ?value WHERE {
  ?o rdf:type cleets:AdoptionRatioObservation ; cleets:forLAD ?lad ; cleets:forTime ?t ; cleets:keeperChargerRatio ?value .
  ?lad rdf:type cleets:WelshLAD ; cleets:ladCode ?code .
  ?t cleets:year ?year ; cleets:quarter ?quarter . }""").rename(columns={"value": "keepers_per_charger"})

pop = q("""
SELECT ?code ?date ?value WHERE {
  ?lad rdf:type cleets:WelshLAD ; cleets:ladCode ?code ; cleets:hasPopulation ?p .
  ?p cleets:populationValue ?value ; dcterms:date ?date . }""")
pop["year"] = pd.to_datetime(pop["date"].astype(str)).dt.year
pop = pop.rename(columns={"value": "population"})[["code", "year", "population"]]

dens = q("""
SELECT ?code ?date ?value WHERE {
  ?lad rdf:type cleets:WelshLAD ; cleets:ladCode ?code ; cleets:hasPopulationDensity ?d .
  ?d cleets:densityValue ?value ; dcterms:date ?date . }""")
dens["year"] = pd.to_datetime(dens["date"].astype(str)).dt.year
dens = dens.rename(columns={"value": "density"})[["code", "year", "density"]].drop_duplicates(["code", "year"])

dep = q("""
SELECT ?code ?value WHERE {
  ?o rdf:type cleets:IncomeDeprivation ; cleets:forLAD ?lad ; cleets:deprivationDecile ?value .
  ?lad rdf:type cleets:WelshLAD ; cleets:ladCode ?code . }""").rename(columns={"value": "income_deprivation_decile"})

key = ["code", "year", "quarter"]
panel = keep
for d in (chg, stock, per1000, per100k, ratio):
    panel = panel.merge(d, on=key, how="outer")
for c in ["year", "quarter"]:
    panel[c] = panel[c].astype(int)
panel = panel.merge(pop, on=["code", "year"], how="left")
panel = panel.merge(dens, on=["code", "year"], how="left")
# carry the latest available population and density forward (mid-2024 is the last estimate)
panel = panel.sort_values(key)
for c in ["population", "density"]:
    panel[c] = panel.groupby("code")[c].transform(lambda s: s.ffill())
panel = panel.merge(dep, on="code", how="left")
panel = panel.merge(lads[["code", "name"]], on="code", how="left").rename(columns={"code": "lad_code", "name": "lad_name"})
panel["period"] = panel["year"].astype(str) + "Q" + panel["quarter"].astype(str)
panel["adoption_share"] = panel["ev_keepership"] / panel["private_stock"]

cols = ["lad_code", "lad_name", "year", "quarter", "period", "ev_keepership", "ev_chargers", "private_stock",
        "adoption_share", "evs_per_1000", "chargers_per_100k", "keepers_per_charger",
        "population", "density", "income_deprivation_decile"]
panel = panel[cols].sort_values(["lad_name", "year", "quarter"]).reset_index(drop=True)
panel.to_csv(out, index=False)
print(panel.shape, panel.period.min(), "to", panel.period.max())
print(panel.notna().sum())
print(panel.head(3).T)
