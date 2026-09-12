trip-planner/
└── backend/
    ├── venv/
    ├── .env
    ├── .env.example
    ├── .gitignore
    ├── requirements.txt
    ├── test_gemini.py       ✅ Gemini connection confirmed
    ├── trip_slots.py         ✅ the "form" schema + question logic
    ├── slot_extraction.py    ✅ context-aware extraction from Gemini
    ├── chat_loop.py          ✅ full terminal conversation working
    ├── geocoding.py     ✅ place name → coordinates (Nominatim)
    ├── distance.py      ✅ straight-line distance (Haversine)
    ├── routing.py       ✅ real driving distance/duration (ORS)
    ├── database.py                                                 ✅ session persistence
    ├── geocoding.py                                                ✅ geocode + reverse_geocode
    ├── routing.py                                                  ✅ real driving distance/duration
    ├── build_train_db.py + trains.db                               ✅ 8,490 trains, 170k stops
    ├── train_lookup.py                                             ✅ station search + train counts
    ├── hubs.py                                                     ✅ nearby bus/train/flight candidates
    ├── build_flight_db.py + flights.db                             ✅ real flight departures (TIR loaded)
    └──




   Nominatim's for to calculate the lan and longitudes...

    🗺️ What is Overpass API (overpassurl)?
    The Overpass API is a read-only API that serves as a powerful search engine for OpenStreetMap raw map data. It allows users to write custom queries to pull specific map features (nodes, ways, and relations) from the OSM database.Core Purpose: Extracting specific map data based on search criteria.How it Works: You send a query written in Overpass QL (Query Language) to an overpassurl (e.g., https://overpass-api.de).Example Use Case: "Find every hospital, public bus stop, or park inside the city boundaries of Hyderabad."What it Outputs: Raw geographic data (GeoJSON, XML, or JSON format) containing the exact coordinates and tags of the requested objects.
    
    🚗 What is OpenRouteService (ORS)?OpenRouteService is a complete open-source geographical information software suite developed by the Heidelberg Institute for Geoinformation Technology. It takes raw OpenStreetMap data and processes it specifically for navigation.Core Purpose: Calculating routes, travel directions, and travel times.How it Works: You send an HTTP request containing start and end coordinates to the ORS API endpoints.Example Use Case: "Give me the fastest driving route from Repudi to Guntur, avoiding toll roads, and tell me how long it will take."What it Outputs: Turn-by-turn navigation instructions, polyline paths to draw on a map, total distance, travel duration, and isochrones (travel time polygons).
    
    