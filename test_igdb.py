#!/usr/bin/env python3
"""Manual IGDB smoke test. Run inside the container:
    docker compose exec retromanager python test_igdb.py
"""
import json

from backend.core import igdb_scraper as igdb  # uses the credentials from Tools > Settings

print("Searching IGDB for 'Sonic the Hedgehog' on megadrive...")
results = igdb.search_game('Sonic the Hedgehog', 'megadrive')
for game in results[:5]:
    print(' ', igdb.summarize_search_result(game))

if results:
    details = igdb.get_game_info(results[0]['id'])
    print("\nMetadata for the first result:")
    print(json.dumps(igdb.extract_game_data(details), indent=2))
