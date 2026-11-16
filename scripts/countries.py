"""国・地域名（公的統計の英語表記）→ ISO 3166-1 alpha-3。地図に置くために使う。

統計ごとに表記が違う（例：U.S.A. / United States of America）ので、別名も登録する。
未登録の名前は iso3() が例外を出す（黙って落とさない）。
"""

ISO3 = {
    "Albania": "ALB", "Andorra": "AND", "Angola": "AGO", "Argentina": "ARG", "Armenia": "ARM",
    "Australia": "AUS", "Austria": "AUT", "Azerbaijan": "AZE", "Bahamas": "BHS", "Bahrain": "BHR",
    "Bangladesh": "BGD", "Barbados": "BRB", "Belarus": "BLR", "Belgium": "BEL", "Benin": "BEN",
    "Bermuda": "BMU", "Bolivia": "BOL", "Brazil": "BRA", "British Virgin Islands": "VGB",
    "Bulgaria": "BGR", "Cameroon": "CMR", "Canada": "CAN", "Cayman Islands": "CYM", "Chile": "CHL",
    "Colombia": "COL", "Costa Rica": "CRI", "Cote d’Ivoire": "CIV", "Croatia": "HRV", "Cuba": "CUB",
    "Curacao": "CUW", "Cyprus": "CYP", "Czech": "CZE", "Denmark": "DNK", "Dominican Republic": "DOM",
    "Ecuador": "ECU", "Egypt": "EGY", "El Salvador": "SLV", "Estonia": "EST", "Ethiopia": "ETH",
    "Finland": "FIN", "France": "FRA", "Gabon": "GAB", "Germany": "DEU", "Ghana": "GHA",
    "Gibraltar": "GIB", "Greece": "GRC", "Guatemala": "GTM", "Guernsey": "GGY", "Honduras": "HND",
    "Hong Kong": "HKG", "Hungary": "HUN", "Iceland": "ISL", "India": "IND", "Indonesia": "IDN",
    "Iraq": "IRQ", "Ireland": "IRL", "Isle of Man": "IMN", "Israel": "ISR", "Italy": "ITA",
    "Jamaica": "JAM", "Jersey": "JEY", "Jordan": "JOR", "Kazakhstan": "KAZ", "Kenya": "KEN",
    "Kuwait": "KWT", "Kyrgyz Republic": "KGZ", "Latvia": "LVA", "Lebanon": "LBN", "Liberia": "LBR",
    "Liechtenstein": "LIE", "Lithuania": "LTU", "Luxembourg": "LUX", "Macau": "MAC", "Malaysia": "MYS",
    "Malta": "MLT", "Marshall": "MHL", "Mauritius": "MUS", "Mexico": "MEX", "Mongolia": "MNG",
    "Montenegro": "MNE", "Morocco": "MAR", "Mozambique": "MOZ", "Namibia": "NAM", "Nepal": "NPL",
    "Netherlands": "NLD", "New Zealand": "NZL", "Nigeria": "NGA", "North Macedonia": "MKD",
    "Norway": "NOR", "Oman": "OMN", "Pakistan": "PAK", "Panama": "PAN", "Papua New Guinea": "PNG",
    "Paraguay": "PRY", "People’s Republic of China": "CHN", "Peru": "PER", "Philippines": "PHL",
    "Poland": "POL", "Portugal": "PRT", "Puerto Rico": "PRI", "Qatar": "QAT",
    "Republic of Congo": "COG", "Republic of Korea": "KOR", "Republic of South Africa": "ZAF",
    "Romania": "ROU", "Russia": "RUS", "Rwanda": "RWA", "Saint Lucia": "LCA", "Saudi Arabia": "SAU",
    "Senegal": "SEN", "Serbia": "SRB", "Singapore": "SGP", "Slovakia": "SVK", "Slovenia": "SVN",
    "Spain": "ESP", "Sri Lanka": "LKA", "Suriname": "SUR", "Sweden": "SWE", "Switzerland": "CHE",
    "Taiwan": "TWN", "Tajikistan": "TJK", "Thailand": "THA", "Togo": "TGO",
    "Trinidad and Tobago": "TTO", "Tunisia": "TUN", "Turkey": "TUR", "Turkmenistan": "TKM",
    "Ukraine": "UKR", "United Arab Emirates": "ARE", "United Kingdom": "GBR",
    "United States Virgin Islands": "VIR", "United States of America": "USA", "Uruguay": "URY",
    "Uzbekistan": "UZB", "Vanuatu": "VUT", "Venezuela": "VEN", "Viet Nam": "VNM", "Zambia": "ZMB",
}

# 別の統計で使われる表記
ISO3.update({
    "Algeria": "DZA",
    "American Samoa": "ASM",
    "Anguilla": "AIA",
    "Belize": "BLZ",
    "Bosnia and Herzegovina": "BIH",
    "British Indian Ocean Territory": "IOT",
    "Brunei": "BRN",
    "Burkina Faso": "BFA",
    "Cambodia": "KHM",
    "Côte d’Ivoire": "CIV",
    "Democratic Republic of the Congo": "COD",
    "Djibouti": "DJI",
    "Fiji": "FJI",
    "Georgia": "GEO",
    "Guam": "GUM",
    "Guyana": "GUY",
    "Iran": "IRN",
    "Lao People's Democratic Republic": "LAO",
    "Libya": "LBY",
    "Madagascar": "MDG",
    "Maldives": "MDV",
    "Micronesia": "FSM",
    "Monaco": "MCO",
    "Myanmar": "MMR",
    "New Caledonia": "NCL",
    "Niger": "NER",
    "Northern Mariana Islands": "MNP",
    "P.R.China": "CHN",
    "Palau": "PLW",
    "R.Korea": "KOR",
    "Saint Christopher and Nevis": "KNA",
    "Samoa": "WSM",
    "San Marino": "SMR",
    "Seychelles": "SYC",
    "Solomon": "SLB",
    "Tanzania": "TZA",
    "Timor-Leste": "TLS",
    "U.K.": "GBR",
    "U.S.A.": "USA",
    "Uganda": "UGA",
})


def norm(name: str) -> str:
    return " ".join(str(name).split())


def iso3(name: str) -> str:
    n = norm(name)
    if n not in ISO3:
        raise KeyError(f"ISO3 未登録の国名: {n!r}")
    return ISO3[n]
