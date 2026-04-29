"""Vehicle information from VIN — NHTSA decode + image lookup.
Works for all makes (Ford, GM, Toyota, etc.) via the free NHTSA VIN decoder API."""
import json
import urllib.request
import urllib.error
import re
import ssl

NHTSA_BASE = "https://vpic.nhtsa.dot.gov/api/vehicles"

# VIN model-year tables. The 10th VIN char codes the year on a 30-year cycle.
# Disambiguation rule: if VIN position 7 is alphabetic the cycle is 2010+,
# if numeric the cycle is 1980-2009.
FORD_YEAR_CODES_1980 = {
    "A": 1980, "B": 1981, "C": 1982, "D": 1983, "E": 1984, "F": 1985,
    "G": 1986, "H": 1987, "J": 1988, "K": 1989, "L": 1990, "M": 1991,
    "N": 1992, "P": 1993, "R": 1994, "S": 1995, "T": 1996, "V": 1997,
    "W": 1998, "X": 1999, "Y": 2000, "1": 2001, "2": 2002, "3": 2003,
    "4": 2004, "5": 2005, "6": 2006, "7": 2007, "8": 2008, "9": 2009,
}

FORD_YEAR_CODES_2010 = {
    "A": 2010, "B": 2011, "C": 2012, "D": 2013, "E": 2014, "F": 2015,
    "G": 2016, "H": 2017, "J": 2018, "K": 2019, "L": 2020, "M": 2021,
    "N": 2022, "P": 2023, "R": 2024, "S": 2025, "T": 2026, "V": 2027,
    "W": 2028, "X": 2029, "Y": 2030, "1": 2031, "2": 2032, "3": 2033,
    "4": 2034, "5": 2035, "6": 2036, "7": 2037, "8": 2038, "9": 2039,
}

# Single-letter plant codes are reused across regions; entries combined
# where both interpretations are plausible.
FORD_PLANT_CODES = {
    "A": "Atlanta, GA",
    "B": "Oakville, ON (Canada)",
    "C": "Ontario Truck, ON (Canada)",
    "D": "Avon Lake, OH",
    "E": "Kentucky Truck, KY / Cologne (Germany)",
    "F": "Dearborn, MI",
    "G": "Chicago, IL / Halewood (UK)",
    "H": "Lorain, OH",
    "I": "Highland Park, MI",
    "J": "Monterrey (Mexico)",
    "K": "Kansas City, MO / General Pacheco (Argentina)",
    "L": "Michigan Truck, MI",
    "M": "Cuautitlán (Mexico)",
    "N": "Norfolk, VA",
    "P": "Twin Cities, MN / Valencia (Spain)",
    "R": "San Jose, CA",
    "S": "Allen Park, MI / Southampton (UK)",
    "T": "Edison, NJ / Çamlıca (Turkey)",
    "U": "Louisville, KY",
    "V": "Kentucky Truck 2, KY / Craiova (Romania)",
    "W": "Wayne, MI / Saarlouis (Germany)",
    "X": "St. Thomas, ON (Canada)",
    "Y": "Wixom, MI",
    "Z": "St. Louis, MO",
    "0": "Detroit Chassis, MI",
    "5": "Flat Rock, MI",
    "8": "Broadmeadows (Australia)",
    "9": "São Bernardo do Campo (Brazil)",
}

WMI_DECODE = {
    "1FA": "Ford Motor Company (USA)",
    "1FB": "Ford Motor Company (USA - Truck)",
    "1FC": "Ford Motor Company (USA - SUV)",
    "1FD": "Ford Motor Company (USA - Incomplete Vehicle)",
    "1FM": "Ford Motor Company (USA - MPV)",
    "1FT": "Ford Motor Company (USA - Truck)",
    "1FU": "Ford Motor Company (USA - Heavy Truck)",
    "1FV": "Ford Motor Company (USA - Medium Truck)",
    "1F6": "Ford Motor Company (USA - Stripped Chassis)",
    "2FA": "Ford Motor Company (Canada)",
    "2FM": "Ford Motor Company (Canada - MPV)",
    "2FT": "Ford Motor Company (Canada - Truck)",
    "3FA": "Ford Motor Company (Mexico)",
    "3FM": "Ford Motor Company (Mexico - MPV)",
    "3FT": "Ford Motor Company (Mexico - Truck)",
    "4FA": "Ford Motor Company (USA - Trucks)",
    "4M2": "Ford Motor Company (USA - Incomplete)",
    "5LJ": "Lincoln (USA)",
    "5LM": "Lincoln (USA - SUV)",
    "5LT": "Lincoln (USA - Truck)",
    "6MP": "Mercury (USA)",
    "7A2": "Ford (New Zealand)",
    "8AF": "Ford (Argentina)",
    "8XD": "Ford (Venezuela)",
    "9BF": "Ford (Brazil)",
    "KNJ": "Ford (South Africa)",
    "LFA": "Ford (Taiwan)",
    "MNB": "Ford (Thailand)",
    "NM0": "Ford (Turkey - Otosan)",
    "PE1": "Ford (Philippines)",
    "PR8": "Ford (Russia)",
    "SFA": "Ford (UK)",
    "TW2": "Ford (Poland)",
    "TW8": "Ford (Germany)",
    "TYA": "Ford (Spain)",
    "VS6": "Ford (Belgium)",
    "WF0": "Ford (Germany - Passenger)",
    "WF1": "Ford (Germany - Trucks)",
    "X9F": "Ford (Russia - Passenger)",
    "XLC": "Ford (Netherlands)",
    "Y4F": "Ford (Romania)",
    "Z6F": "Ford (Russia)",
}


def _fetch_json(url: str, timeout: float = 10.0) -> dict:
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={"User-Agent": "FUSE/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return {}


def decode_vin(vin: str) -> dict:
    """Decode a 17-character VIN using NHTSA API with local fallback."""
    vin = vin.strip().upper()
    if len(vin) != 17:
        return {"error": f"Invalid VIN length: {len(vin)} chars (expected 17)", "vin": vin}

    info = {
        "vin": vin,
        "wmi": vin[:3],
        "vds": vin[3:8],
        "check_digit": vin[8],
        "model_year_code": vin[9],
        "plant_code": vin[10],
        "serial": vin[11:],
    }

    # Try NHTSA decode
    data = _fetch_json(f"{NHTSA_BASE}/DecodeVin/{vin}?format=json")
    results = data.get("Results", [])

    if results:
        for r in results:
            var = r.get("Variable", "")
            val = r.get("Value", "")
            if not val or val in ("Not Applicable", "Not Found", "Unknown", "0"):
                continue
            if var == "Make":
                info["make"] = val
            elif var == "Model":
                info["model"] = val
            elif var == "Model Year":
                info["year"] = val
            elif var == "Plant Country":
                info["plant_country"] = val
            elif var == "Plant City":
                info["plant_city"] = val
            elif var == "Plant State":
                info["plant_state"] = val
            elif var == "Manufacturer Name":
                info["manufacturer"] = val
            elif var == "Vehicle Type":
                info["vehicle_type"] = val
            elif var == "Body Class":
                info["body_class"] = val
            elif var == "Doors":
                info["doors"] = val
            elif var == "Engine Number of Cylinders":
                info["cylinders"] = val
            elif var == "Displacement (L)":
                info["displacement_l"] = val
            elif var == "Engine Model":
                info["engine"] = val
            elif var == "Fuel Type - Primary":
                info["fuel_type"] = val
            elif var == "Transmission Style":
                info["transmission"] = val
            elif var == "Drive Type":
                info["drive_type"] = val
            elif var == "Gross Vehicle Weight Rating From":
                info["gvwr"] = val
            elif var == "Trim":
                info["trim"] = val
            elif var == "Series":
                info["series"] = val
            elif var == "Brake System Type":
                info["brake_type"] = val
            elif var == "Engine Brake (hp) From":
                info["horsepower"] = val
            elif var == "Seat Belt Type":
                info["seat_belt_type"] = val
            elif var == "Air Bag Loc Front":
                info["airbags_front"] = val
            elif var == "Air Bag Loc Side":
                info["airbags_side"] = val
            elif var == "Plant Company Name":
                info["plant_name"] = val
            elif var == "Note":
                info["notes"] = val

    # Fallback: decode model year from VIN position 10. Position 7 disambiguates
    # the 30-year cycle: alphabetic = 2010-2039, numeric = 1980-2009.
    if "year" not in info:
        yc = vin[9]
        cycle = FORD_YEAR_CODES_2010 if vin[6].isalpha() else FORD_YEAR_CODES_1980
        year = cycle.get(yc)
        info["year"] = str(year) if year else "Unknown"

    # Fallback: decode assembly plant
    if "plant_city" not in info and "plant_country" not in info:
        pc = vin[10]
        info["plant_name"] = FORD_PLANT_CODES.get(pc, f"Plant code: {pc}")

    # Fallback: WMI decode
    if "make" not in info:
        info["make"] = WMI_DECODE.get(vin[:3], "Unknown manufacturer")

    # Construct where-it-was-made string
    parts = []
    if info.get("plant_city"):
        parts.append(info["plant_city"])
    if info.get("plant_state"):
        parts.append(info["plant_state"])
    if info.get("plant_country"):
        parts.append(info["plant_country"])
    if not parts and info.get("plant_name"):
        parts.append(info["plant_name"])
    info["built_at"] = ", ".join(parts) if parts else "Unknown"

    return info


def get_vehicle_image_url(vin: str, make: str = "", model: str = "", year: str = "") -> str:
    """Try to find a vehicle image from multiple free sources."""
    # Carfax often has VIN-based images
    carfax_url = f"https://media.carfax.com/img/vrp/640/{vin}.jpg"
    if _url_exists(carfax_url):
        return carfax_url

    # Try carfax with VIN in different format
    carfax_url2 = f"https://images.carfax.com/v2/{vin}_01.jpg"
    if _url_exists(carfax_url2):
        return carfax_url2

    # For Ford vehicles, try Ford's owner site
    if make and "ford" in make.lower():
        ford_url = f"https://www.ford.com/support/discover-your-ford/vehicle-selector/?vin={vin}"
        return ford_url  # Returns the Ford vehicle selector page URL

    # Try a generic approach - NHTSA sometimes has images
    return ""


def _url_exists(url: str) -> bool:
    try:
        ctx = ssl.create_default_context()
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "FUSE/1.0"})
        with urllib.request.urlopen(req, timeout=5, context=ctx) as resp:
            return resp.status == 200
    except Exception:
        return False


def format_vehicle_summary(info: dict) -> str:
    """Format vehicle info into a readable summary for the AI mechanic."""
    lines = []
    if info.get("year"):
        lines.append(f"Year: {info['year']}")
    if info.get("make"):
        lines.append(f"Make: {info['make']}")
    if info.get("model"):
        lines.append(f"Model: {info['model']}")
    if info.get("engine"):
        lines.append(f"Engine: {info['engine']} ({info.get('cylinders','?')}cyl, {info.get('displacement_l','?')}L)")
    if info.get("transmission"):
        lines.append(f"Transmission: {info['transmission']}")
    if info.get("drive_type"):
        lines.append(f"Drive: {info['drive_type']}")
    if info.get("fuel_type"):
        lines.append(f"Fuel: {info['fuel_type']}")
    if info.get("body_class"):
        lines.append(f"Body: {info['body_class']}{' (' + info['doors'] + ' door)' if info.get('doors') else ''}")
    if info.get("trim"):
        lines.append(f"Trim: {info['trim']}")
    if info.get("gvwr"):
        lines.append(f"GVWR: {info['gvwr']} lbs")
    if info.get("built_at"):
        lines.append(f"Built: {info['built_at']}")
    if info.get("horsepower"):
        lines.append(f"Horsepower: {info['horsepower']} hp")
    if info.get("notes"):
        lines.append(f"Notes: {info['notes']}")
    return "\n".join(lines)
