# MTG Store Card Search

`tcg-local` searches TCGplayer store inventories for wanted Magic: The Gathering cards in selected cities or ZIP codes. It ranks stores by how many wanted cards they have, then by the combined price of the cheapest matching copies.

`tcg-seller` is a separate, experimental program that searches a known public
TCGplayer seller page without an API key or account login.

`wizards-stores` discovers physical Magic stores near one or more cities using
the public Wizards Store Locator.

## Find physical stores

```bash
wizards-stores \
  --city Houston \
  --city Dallas \
  --state TX \
  --radius-miles 10
```

The output includes the store name, address, distance, Wizards store ID, and
the city searches that matched it. Use `--format json` for the additional
coordinates, phone, website, and WPN Premium flag.

Add `--resolve-tcgplayer` to search TCGplayer's public seller directory for an
exact normalized store-name match:

```bash
wizards-stores \
  --city Houston \
  --state TX \
  --radius-miles 10 \
  --resolve-tcgplayer
```

Name normalization ignores capitalization, punctuation, and the difference
between `&` and `and`. Partial matches are reported but never selected
automatically.

This command starts an anonymous locator session so Wizards can set its normal
site cookies, but it never accepts account credentials or stores cookies after
the process exits.

## Public seller search (no API key)

Once you know a seller's public page, search it directly:

```bash
tcg-seller \
  --seller-url 'https://www.tcgplayer.com/sellers/Black-Castle-Gamez/b31b0b79' \
  --card 'Wind Strider'
```

Repeat `--card` or use `--cards-file cards.txt`. Add `--format json` for
machine-readable output. The program never asks for TCGplayer credentials and
does not store browser cookies.

Card searches use four workers by default while sharing the global request
interval. Use `--workers 1` to search sequentially.

This mode uses the same anonymous JSON request as TCGplayer's public seller
storefront. It is not part of the documented developer API and may change
without notice. Requests are still spaced at least 0.5 seconds apart and use
the fixed 60-second and 3-minute retry schedule.

## Important API limitation

TCGplayer requires an existing API developer key and no longer grants new API access. This program cannot bypass that restriction. If you already have a `PUBLIC_KEY` and `PRIVATE_KEY`, keep them private and provide them through environment variables.

Store discovery and store inventory are separate permissions. The [Search Stores documentation](https://docs.tcgplayer.com/reference/stores_getstores-1) says search results cannot be used to interact with the returned stores, so arbitrary local-store inventory may be unavailable. Inventory lookup can require the individual store to follow TCGplayer's [Store Authorization Workflow](https://docs.tcgplayer.com/docs/store-authorization-workflow). The program keeps other results when one store rejects an inventory request and displays the rejection under `Inventory request errors`.

An optional `TCGPLAYER_ACCESS_TOKEN` is supported for applications that a particular TCGplayer store has explicitly authorized. Do not confuse that store authorization token with the short-lived OAuth bearer token; this program obtains the bearer token automatically.

## Install

Python 3.11 or newer is required.

```bash
cd mtg-store-card-search
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

Set credentials in the current shell. Do not paste them into source code or commit them to Git.

```bash
export TCGPLAYER_PUBLIC_KEY='your-public-key'
export TCGPLAYER_PRIVATE_KEY='your-private-key'
```

If a store authorized the application, also set:

```bash
export TCGPLAYER_ACCESS_TOKEN='the-store-authorization-key'
```

Verify authentication:

```bash
tcg-local doctor
```

## Quick search

Search several cities for any English printing of two cards:

```bash
tcg-local find \
  --city Houston \
  --city Dallas \
  --city 'San Antonio' \
  --city 'Fort Worth' \
  --city 'El Paso' \
  --state TX \
  --card 'Basilisk Collar' \
  --card 'Blade of the Bloodchief'
```

For a longer list, create a text file with one card name per line and use `--cards-file cards.txt`.

## Exact printings and conditions

Copy `request.example.json`, edit it, and run:

```bash
tcg-local find --request request.example.json
```

Each card object supports:

- `name` — required card name
- `set` — exact TCGplayer group/set name
- `number` — exact collector number
- `condition` — for example, `Near Mint`
- `language` — defaults to `English`; use `null` for any language
- `finish` — `any`, `foil`, or `nonfoil`

Each area supports `city` plus `state`, or `zip_code` plus `state`.

## Output formats

The default table shows store coverage and the cheapest total. Machine-readable formats are also available:

```bash
tcg-local find --request request.example.json --format json > results.json
tcg-local find --request request.example.json --format csv > results.csv
```

Use `--include-empty` to include stores with no matches. Use `--workers 1` if a credential's rate limit is particularly restrictive.

API request starts are spaced at least 0.5 seconds apart across all worker threads. Retryable failures wait 60 seconds before the first retry and 3 minutes before the final retry. A third failure ends that request.

## Store discovery only

```bash
tcg-local stores --city Houston --city Dallas --state TX
```

## Tests

Tests use fake API responses and do not require credentials or network access.

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

## What the program calls

- `POST https://api.tcgplayer.com/token`
- `GET /v1.39.0/stores` with city, state, or ZIP filters
- `GET /v1.39.0/stores/{storeKeys}` for store names and storefront URLs
- `GET /v1.39.0/stores/{storeKey}/inventory/products` with `categoryName=Magic` and `productName`

Inventory changes quickly. Treat results as a lead and reserve cards with the store before making a long trip.
