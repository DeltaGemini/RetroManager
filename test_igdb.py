#!/usr/bin/env python3
"""Manual IGDB smoke test. Run inside the container:
    docker compose exec retromanager python test_igdb.py
"""
import json
import os

from backend.igdb_scraper import IGDBAPI

if not (os.getenv('IGDB_CLIENT_ID') and os.getenv('IGDB_CLIENT_SECRET')):
    raise SystemExit("Set IGDB_CLIENT_ID and IGDB_CLIENT_SECRET first.")
igdb = IGDBAPI(os.environ['IGDB_CLIENT_ID'], os.environ['IGDB_CLIENT_SECRET'])

print("Searching IGDB for 'Sonic the Hedgehog' on megadrive...")
results = igdb.search_game('Sonic the Hedgehog', 'megadrive')
for game in results[:5]:
    print(' ', igdb.summarize_search_result(game))

if results:
    details = igdb.get_game_info(results[0]['id'])
    print("\nMetadata for the first result:")
    print(json.dumps(igdb.extract_game_data(details), indent=2))
