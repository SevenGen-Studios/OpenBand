"""Merge source-verified Alberta announcements without replacing existing records."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENERGY = "https://www.canada.ca/en/natural-resources-canada/news/2026/07/backgrounder-canada-invests-in-clean-energy-in-alberta-and-saskatchewan.html"
FOREST = "https://www.canada.ca/en/natural-resources-canada/news/2025/10/canada-backs-indigenous-led-growth-in-prairie-forest-sectors0.html"
PARK = "https://www.canada.ca/en/prairies-economic-development/news/2026/07/government-of-canada-powering-long-term-sustainability-and-indigenous-knowledge-sharing-at-blackfoot-crossing-historical-park.html"
ROAD = "https://www.canada.ca/en/indigenous-services-canada/news/2019/07/little-red-river-cree-nation-benefits-from-several-infrastructure-improvements.html"
NET = "https://www.canada.ca/en/housing-infrastructure-communities/news/2021/06/canada-and-alberta-announce-two-broadband-and-wireless-projects-in-indigenous-communities.html"


def records():
    groups = [
        (ENERGY, "Natural Resources Canada", "2026-07-04", [
            ("blood-wind-capacity", ["435"], "Renewable Energy", "Wind project pre-development", "Studies, permitting and workforce preparation for a proposed wind farm.", "Federal funding: $2,000,000"),
            ("ermineskin-solar-feasibility", ["443"], "Renewable Energy", "Solar and storage feasibility", "Feasibility work for solar generation and battery storage.", "Federal funding: $1,479,750"),
            ("samson-solar-development", ["444"], "Renewable Energy", "Solar pre-development", "Preparation for a Nation-majority-owned solar installation.", "NRCan: $781,740; ISC: $208,830"),
            ("saddle-lake-solar-storage", ["462"], "Renewable Energy", "Solar and storage planning", "Site assessment, environmental studies and training for renewable energy.", "NRCan: $684,750; ISC: $228,250"),
            ("bigstone-energy-feasibility", ["458"], "Renewable Energy", "Renewable energy feasibility", "Energy modeling, site assessment, community engagement and workforce training.", "NRCan: $637,950; ISC: $212,650"),
            ("newo-clean-energy-training", ["437", "442"], "Education", "Clean energy training", "Newo Global Energy training program involving Alexis and Montana communities. Funding is shared, not allocated per Nation.", "Program funding: $461,756"),
            ("samson-energy-planning", ["444"], "Renewable Energy", "Community energy planning", "Energy priorities, workshops and local capacity development.", "Federal funding: $353,863"),
            ("frog-lake-building-efficiency", ["465"], "Housing", "Housing energy-code capacity", "Staff training and tools for energy-efficient community housing standards.", "Federal funding: $1,321,997"),
        ]),
        (FOREST, "Natural Resources Canada", "2025-10-24", [
            ("cold-lake-firewood-equipment", ["464"], "Economic Development", "Forestry equipment investment", "Equipment acquisition to expand salvage timber processing.", "Federal funding: $129,500"),
            ("little-red-river-mulchers", ["447"], "Economic Development", "Forestry mulcher acquisition", "Equipment investment supporting the Nation's forest-sector participation.", "Federal funding: $119,500"),
            ("lubicon-tiny-homes-study", ["453"], "Housing", "Tiny homes and forestry feasibility", "Analysis of forestry manufacturing and a possible tiny-home enterprise; not a confirmed housing build.", "Federal funding: $20,000"),
            ("athabasca-wood-heating-study", ["463"], "Renewable Energy", "Wood heating feasibility", "Study of wood-fuel heating opportunities in Fort Chipewyan.", "Federal funding: $50,000"),
            ("tsuutina-forestry-development", ["432"], "Economic Development", "Forestry skills development", "Forest-based skills and economic opportunities for community members.", "Federal funding: $105,720"),
            ("swan-river-bioenergy", ["457"], "Renewable Energy", "Community bioenergy development", "Development support for heat and power serving homes and community facilities.", "Federal funding: $350,000"),
            ("siksika-forest-stewardship", ["430"], "Environment", "Forest stewardship and cultural knowledge", "Documenting cultural knowledge and training members for forest-management planning.", "Federal funding: $50,000"),
        ]),
        (PARK, "Prairies Economic Development Canada", "2026-07-13", [
            ("blackfoot-crossing-solar-planning", ["430"], "Renewable Energy", "Blackfoot Crossing solar planning", "Community engagement and investigation of possible solar sites at Blackfoot Crossing Historical Park.", "Federal funding: $93,000"),
        ]),
        (NET, "Housing, Infrastructure and Communities Canada", "2021-06-28", [
            ("saddle-lake-broadband-upgrade", ["462"], "Connectivity", "Broadband and cellular upgrades", "Announced network upgrades. Funding was conditional; the announcement does not verify completion.", "Federal funding: more than $2.6 million"),
            ("cold-lake-wireless-upgrade", ["464"], "Connectivity", "Wireless network upgrades", "Announced LTE equipment for existing and new towers. Completion is not established by this source.", "Federal funding: $241,544"),
        ]),
        (ROAD, "Indigenous Services Canada", "2019-07-19", [
            ("fox-lake-access-road", ["447"], "Roads & Transportation", "Fox Lake access road", "ISC reported completion of the all-weather access road in July 2019.", None),
            ("john-dor-primary-care", ["447"], "Health", "John D'Or Prairie Primary Care Centre", "ISC reported completion of a replacement health centre with primary care and telemedicine services in July 2019.", None),
            ("little-red-river-school-upgrades", ["447"], "Education", "Three-community school upgrades", "School renovations and expansions in John D'Or Prairie, Fox Lake and Garden River were reported complete in July 2019.", None),
            ("little-red-river-sixteen-homes", ["447"], "Housing", "Sixteen new homes", "ISC reported 16 homes constructed or procured in July 2019. No individual project cost is disclosed.", None),
        ]),
    ]
    result = []
    for url, source, date, rows in groups:
        for ident, bands, category, name, description, funding in rows:
            row = dict(id=ident, firstNationIds=bands, category=category, name=name,
                       description=description, lastVerifiedAt="2026-10-01",
                       sources=[dict(name=source, url=url, publishedAt=date)])
            if funding:
                row["funding"] = [funding]
            if url == ROAD:
                row.update(status="Completed", statusAsOf=date)
            result.append(row)
    result.extend(additional_records())
    return result


def additional_records():
    """Reviewed project descriptions; registry determinations are not completions."""
    rows = [
        ("chiniki-goodstoney-solar", ["433", "475"], "Renewable Energy", "Deerfoot and Barlow solar facilities", "The federal green-bond report identifies Chiniki and Goodstoney's combined 51% ownership and reports the facilities operational in November 2023. Shared financing is not allocated to each Nation.", "https://www.canada.ca/en/department-finance/programs/financial-sector-policy/securities/debt-program/green-bond-allocation-impact-report-2023-24.html", None),
        ("fort-mckay-guardians", ["467"], "Environment", "Environmental Guardians initiative", "Federal 2025-2026 support of $175,000 covers environmental monitoring, stewardship and related community activities; this is program funding, not a construction cost.", "https://www.canada.ca/en/environment-climate-change/news/2025/12/47-first-nations-guardians-initiatives-20252026.html", "2025-12-17"),
        ("whitefish459-wetland-mapping", ["459"], "Environment", "Vegetation and wetland mapping", "Federal 2025-2026 support of $361,791 funds vegetation, wetland and habitat mapping for Whitefish Lake #459, distinct from #128.", "https://www.canada.ca/en/environment-climate-change/news/2025/12/16-first-nations-indigenous-led-natural-climate-solutions-initiatives-20252026.html", "2025-12-17"),
        ("louis-bull-daycare-solar", ["439"], "Renewable Energy", "Daycare solar installation and skills training", "The delivery partner reports a daycare solar installation by Solar Skills graduates in October 2017. No project cost is disclosed here.", "https://www.enbridge.com/stories/archived/2017/november/iron-and-earth-solar-skills-energy-tradespeople-indigenous-workers", None),
        ("three-nations-solar", ["461", "463"], "Renewable Energy", "Three Nations Energy solar project", "The federal announcement describes a jointly owned solar and storage project involving Mikisew Cree, Athabasca Chipewyan and Fort Chipewyan Metis partners. This 2019 announcement does not verify completion.", "https://www.canada.ca/en/natural-resources-canada/news/2019/08/solar-energy-moves-indigenous-communities-toward-a-renewable-future.html", "2019-08-08"),
        ("loon-river-lagoon-tender", ["476"], "Water & Wastewater", "Sewage lagoon upgrades tender", "The engineering procurement notice invited bids for lagoon upgrades with a July 2, 2025 deadline. A tender does not establish award, expenditure or completion.", "https://ae-ab.bidsandtenders.ca/Module/Tenders/en/Tender/Detail/f64d9685-2eb0-4a88-9ca9-b101ad752c71", None),
        ("beaver-timber-planning", ["445"], "Economic Development", "Timber harvesting feasibility", "Feasibility and business planning for Beaver Nation Timber Harvesting Naatsii Limited Partnership. NRCan reported $47,200 in support.", "https://www.canada.ca/en/natural-resources-canada/news/2026/03/government-of-canada-invests-in-strengthening-the-prairies-forest-sector.html", "2026-03-06"),
        ("duncans-water-plant", ["451"], "Water & Wastewater", "New water treatment plant", "ISC announced the opening of the replacement plant, reservoir and raw-water supply, supported by approximately $13 million.", "https://www.canada.ca/en/indigenous-services-canada/news/2024/03/duncans-first-nation-celebrates-the-opening-of-a-new-water-treatment-plant.html", "2024-03-01"),
        ("tallcree-south-water-plant", ["446"], "Water & Wastewater", "South Tallcree water treatment plant", "The federal announcement documents the plant's grand opening and approximately $10 million in investment over four years.", "https://www.canada.ca/en/news/archive/2014/06/harper-government-supports-grand-opening-tallcree-first-nation-water-treatment-plant.html", "2014-06-26"),
        ("horse-lake-water-plant", ["449"], "Water & Wastewater", "Water treatment plant", "Alberta's project registry identifies Horse Lake First Nation as developer and lists the plant as completed. Registry schedules are not exact completion dates.", "https://majorprojects.alberta.ca/details/Horse-Lake-Water-Treatment-Plant", None),
        ("paul-k9-school", ["441"], "Education", "K-9 school", "Alberta's registry identifies Paul First Nation as developer of the school on Wabamun 133A and lists the project as completed.", "https://majorprojects.alberta.ca/details/Paul-First-Nation-Reserve-K-9-School", None),
        ("sturgeon-water-upgrades", ["455"], "Water & Wastewater", "Emergency water treatment plant upgrades", "The provincial registry describes proposed upgrades to the existing treatment system. The listed schedule is prospective, not proof of completion.", "https://www.majorprojects.alberta.ca/details/Sturgeon-Lake-Cree-Nation-Emergency-Water-Treatment-Plant-Upgrades/11937", None),
        ("ochiese-new-school", ["431"], "Education", "Ne Sah Soh Is Koh Dahn School", "The federal announcement records the opening of a new K4-to-Grade-12 school serving 375 students.", "https://www.canada.ca/en/indigenous-northern-affairs/news/2016/09/government-canada-congratulates-chiese-first-nation-new-school.html", "2016-09-19"),
        ("peerless-admin-office", ["478"], "Community Facilities", "Administration office", "The federal announcement confirms a new administration office funded through the Nation's settlement trust. The trust balance is not the office cost.", "https://www.canada.ca/en/indigenous-northern-affairs/news/2017/11/the_government_ofcanadacongratulatespeerlesstroutfirstnationonne.html", "2017-11-20"),
        ("piikani-school-funding", ["436"], "Education", "New K-12 school funding", "ISC announced funding for a new school intended to accommodate 600 students. This announcement does not establish construction completion.", "https://www.canada.ca/en/indigenous-services-canada/news/2024/10/new-school-funding-to-provide-successful-career-pathways-for-piikani-nation-youth.html", "2024-10-17"),
        ("beaver-lake-education-facility", ["460"], "Education", "Energy-efficient education facility", "The federal announcement commits more than $16.1 million to a new education facility; completion is not established by this source.", "https://www.canada.ca/en/housing-infrastructure-communities/news/2023/12/federal-government-announces-investment-in-energy-efficient-education-facility-in-beaver-lake-cree-nation.html", "2023-12-05"),
        ("amisk-school-solar", ["460"], "Renewable Energy", "Amisk Community School solar installation", "The community's project page describes a two-phase, 94-panel installation and associated training. The undated page does not establish a completion year.", "https://beaverlakecreenation.ca/amisk-community-school/amisk-solar-project/", None),
        ("chateh-water-treatment", ["448"], "Water & Wastewater", "Chateh water treatment plant", "The federal announcement records the opening of a membrane and ultraviolet treatment plant, supported by $12 million in federal investment.", "https://www.canada.ca/en/news/archive/2011/05/minister-duncan-congratulates-dene-tha-first-nation-opening-state-art-water-treatment-plant-alberta.html", "2011-05-20"),
        ("yellowhead-belvedere-housing", ["431", "434", "438", "437"], "Housing", "Yellowhead Tribal Council affordable housing", "The Tribal Council announced a groundbreaking for 149 mixed-income units in Edmonton, explicitly serving its four member Nations. No per-Nation funding allocation is reported.", "https://yellowheadtribalcouncil.ca/news-and-events/first-nations-affordable-housing/", "2025-10-01"),
        ("fort-mcmurray-park-pavilion", ["468"], "Community Facilities", "Community park and pavilion", "The project's architect identifies Fort McMurray #468 First Nation as client and reports completion in 2022.", "https://www.tawarc.com/all-projects/fort-mcmurray-468-first-nation-community-park-and-pavilion", None),
        ("kehewin-school-announcement", ["466"], "Education", "Elementary school investment", "The 2009 federal announcement describes a proposed K-6 school and funding commitments. It does not verify completion.", "https://www.canada.ca/en/news/archive/2009/07/government-canada-delivers-new-school-kehewin-cree-nation-alberta.html", "2009-07-21"),
    ]
    registry = [
        ("woodland-five-homes", ["474"], "Housing", "Five-unit residential development", "Proposed five ready-to-move homes and servicing on reserves 226 and 228.", "89288", "2025-02-18"),
        ("woodland-marten-housing", ["474"], "Housing", "Marten Lake housing and servicing", "Proposed ten housing units with water, sewer and roads.", "83809", "2022-07-15"),
        ("woodland-simon-housing", ["474"], "Housing", "Simon Lake housing and servicing", "Proposed 21 housing units with associated services.", "83810", "2022-07-15"),
        ("woodland-fibre-network", ["474"], "Connectivity", "Fibre-to-the-home network", "Proposed broadband network connecting 303 household points along approximately 75 kilometres of roads.", "89576", "2025-05-29"),
        ("kapawe-sucker-broadband", ["452", "456"], "Connectivity", "Existing tower antenna upgrades", "Proposed antenna upgrades on two existing towers serving reserves 150A and 150B.", "87431", "2024-03-19"),
        ("sucker-three-homes", ["456"], "Housing", "Three modular housing lots", "Proposed modular housing lots within an existing subdivision.", "82944", "2021-08-31"),
        ("driftpile-rapid-housing", ["450"], "Housing", "Rapid Housing development", "Proposed 24 units in three eight-unit buildings.", "84462", "2023-03-31"),
        ("driftpile-three-homes", ["450"], "Housing", "Three residential homes", "Proposed homes on lots 408, 409 and 410, separate from the Rapid Housing development.", "84626", "2023-05-24"),
        ("enoch-millennium-servicing", ["440"], "Housing", "Millennium Housing infrastructure", "Proposed enabling infrastructure for approximately 166 residential units.", "90788", "2026-09-18"),
        ("chipewyan-prairie-wastewater", ["470"], "Water & Wastewater", "Wastewater lagoon and sewer infrastructure", "Proposed wastewater lagoon, pump station and sewer line.", "81132", "2020-11-10"),
        ("chipewyan-prairie-gas", ["470"], "Infrastructure", "Janvier gas extension", "Proposed phase-two gas extension of approximately 500 metres serving seven homes.", "89661", "2025-06-19"),
        ("heart-lake-water-plant", ["469"], "Water & Wastewater", "Water treatment plant and intake", "Proposed new treatment plant and water intake.", "89358", "2025-03-11"),
        ("heart-lake-bridge", ["469"], "Roads & Transportation", "Piche River bridge replacement", "Proposed replacement of bridge BF80752 on the community access road.", "80936", "2020-08-14"),
        ("duncans-subdivision", ["451"], "Housing", "Twenty-two-unit subdivision", "Proposed subdivision with roads, water and sewer infrastructure.", "88567", "2024-05-21"),
        ("sawridge-two-homes", ["454"], "Housing", "Two-home housing project", "Proposed single-family housing project for 2025-2026.", "89956", "2025-12-08"),
        ("whitefish128-subdivision", ["ab-whitefish-lake-128"], "Housing", "Great Plains Road subdivision", "Proposed grading, drainage and servicing for 15 lots at Whitefish Lake #128, not Whitefish Lake #459.", "90324", "2026-03-27"),
        ("whitefish128-cisterns", ["ab-whitefish-lake-128"], "Water & Wastewater", "Household cistern replacements and repairs", "Proposed 224 cistern replacements and 38 repairs at Whitefish Lake #128.", "85715", "2023-06-26"),
        ("bearspaw-eden-water", ["473"], "Water & Wastewater", "Eden Valley treatment plant replacement", "Proposed replacement of the water treatment plant destroyed by fire in 2022.", "89659", "2025-06-19"),
    ]
    for ident, bands, category, name, description, registry_id, date in registry:
        rows.append((ident, bands, category, name,
                     description + " Registry assessment decisions do not verify construction completion.",
                     f"https://iaac-aeic.gc.ca/050/evaluations/proj/{registry_id}?culture=en-CA", date))
    result = []
    for ident, bands, category, name, description, url, date in rows:
        source = {"name": "Canadian Impact Assessment Registry" if "iaac-aeic" in url else
                  "Government of Canada" if "canada.ca" in url else
                  "Alberta Major Projects" if "majorprojects.alberta" in url else
                  "Project owner or delivery partner", "url": url}
        source["publishedAt" if date else "checkedAt"] = date or "2026-10-01"
        result.append(dict(id=ident, firstNationIds=bands, category=category,
                           name=name, description=description,
                           lastVerifiedAt="2026-10-01", sources=[source]))
    return result


def main():
    path = ROOT / "projects-data.json"
    payload = json.loads(path.read_text())
    existing = {row["id"] for row in payload["projects"]}
    additions = [row for row in records() if row["id"] not in existing]
    payload["projects"].extend(additions)
    payload["generatedAt"] = "2026-10-01"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    bands = json.loads((ROOT / "data.json").read_text())["bands"]
    alberta = [b for b in bands if b.get("province") == "AB"]
    ids = {str(b["id"]) for b in alberta}
    projects = [r for r in payload["projects"] if ids.intersection(map(str, r["firstNationIds"]))]
    covered = {str(i) for r in projects for i in r["firstNationIds"]} & ids
    report = {
        "checkedAt": "2026-10-01",
        "scope": "Reviewed official announcements; not an exhaustive Alberta project inventory",
        "trackedCommunities": len(alberta),
        "communitiesWithVerifiedProjects": len(covered),
        "verifiedProjectRecords": len(projects),
        "coveragePercent": round(len(covered) / len(alberta) * 100, 2),
        "sourcesReviewed": sorted({s["url"] for r in records() for s in r["sources"]}),
        "communitiesWithoutIndexedProjects": [
            {"bandId": str(b["id"]), "name": b["name"]}
            for b in alberta if str(b["id"]) not in covered
        ],
        "limitations": [
            "No indexed project does not imply no projects exist.",
            "Funding announcements are not evidence of expenditure or completion.",
            "Historical completion claims retain the source announcement date.",
            "Shared program funding is not assigned separately to participating Nations.",
        ],
    }
    (ROOT / "alberta-project-coverage-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    print(f"Added {len(additions)} source-backed Alberta projects")


if __name__ == "__main__":
    main()
