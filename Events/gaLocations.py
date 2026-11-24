"""
gaLocations.py — Georgia cities and public high schools for the
volunteer filter row. City -> schools mapping narrows the school
list when a city is chosen.
"""

ga_cities = [
    "Atlanta", "Augusta", "Columbus", "Macon", "Savannah",
    "Athens", "Sandy Springs", "Roswell", "Johns Creek", "Albany",
    "Warner Robins", "Alpharetta", "Marietta", "Valdosta", "Smyrna",
    "Dunwoody", "Peachtree City", "Newnan", "Gainesville", "Dalton",
    "Hinesville", "Statesboro", "Carrollton", "LaGrange", "Douglasville",
    "Lawrenceville", "Duluth", "Kennesaw", "Rome", "Brunswick",
]

GA_HIGH_SCHOOLS = {
    "Atlanta": [
        "North Atlanta High School", "Midtown High School",
        "Maynard Jackson High School", "Frederick Douglass High School",
        "Benjamin E. Mays High School",
    ],
    "Augusta": [
        "Laney High School", "Richmond Academy",
        "Westside High School", "Josey High School",
    ],
    "Columbus": [
        "Hardaway High School", "Carver High School",
        "Columbus High School", "Jordan Vocational High School",
    ],
    "Macon": [
        "Central High School", "Howard High School",
        "Northeast High School", "Rutland High School",
    ],
    "Savannah": [
        "Savannah Arts Academy", "Jenkins High School",
        "Johnson High School", "Beach High School",
    ],
    "Athens": [
        "Cedar Shoals High School", "Clarke Central High School",
    ],
    "Sandy Springs": ["North Springs High School"],
    "Roswell": ["Roswell High School", "Centennial High School"],
    "Johns Creek": ["Johns Creek High School", "Chattahoochee High School"],
    "Alpharetta": ["Alpharetta High School", "Cambridge High School"],
    "Marietta": ["Marietta High School", "Walton High School"],
    "Lawrenceville": ["Central Gwinnett High School"],
    "Duluth": ["Duluth High School"],
    "Kennesaw": ["Kennesaw Mountain High School", "North Cobb High School"],
    "Rome": ["Rome High School"],
    "Valdosta": ["Valdosta High School", "Lowndes High School"],
    "Gainesville": ["Gainesville High School"],
    "Dalton": ["Dalton High School"],
    "Statesboro": ["Statesboro High School"],
    "Carrollton": ["Carrollton High School"],
    "Douglasville": ["Alexander High School", "Douglas County High School"],
    "Brunswick": ["Brunswick High School", "Glynn Academy"],
    "Albany": ["Albany High School", "Dougherty Comprehensive High"],
    "Warner Robins": ["Warner Robins High School", "Houston County High"],
    "Newnan": ["Newnan High School", "East Coweta High School"],
    "Peachtree City": ["McIntosh High School", "Starr's Mill High School"],
    "Hinesville": ["Bradwell Institute", "Liberty County High School"],
    "LaGrange": ["LaGrange High School", "Troup County High School"],
    "Smyrna": ["Campbell High School"],
    "Dunwoody": ["Dunwoody High School"],
}

ALL_CITIES = "All cities"
ALL_SCHOOLS = "All schools"


def schools_for_city(city):
    if city and city in GA_HIGH_SCHOOLS:
        return GA_HIGH_SCHOOLS[city]
    flat = []
    for schools in GA_HIGH_SCHOOLS.values():
        flat.extend(schools)
    return sorted(set(flat))
