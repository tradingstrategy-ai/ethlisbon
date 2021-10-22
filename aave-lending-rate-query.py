"""Pull historical Aave lending rates.

Based on the reverse engineered https://aavescan.com/reserve/0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb480xb53c1a33016b2dc2ff3653530bff1848a515c8c5?version=v2
"""
import sys
import json
import requests
import datetime

# https://towardsdatascience.com/connecting-to-a-graphql-api-using-python-246dda927840
example_query = """
{
  "variables": {
    "reserve": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb480xb53c1a33016b2dc2ff3653530bff1848a515c8c5"
  },
  
  "query": "query ($reserve: String!) {
    t1634842615: reserveParamsHistoryItems(
        first: 1, where: {reserve: $reserve, timestamp_gt: 1634842615, timestamp_lt: 1634851415}) {
        liquidityRate
        priceInUsd
        timestamp
        __typename 
    }"
}
 """

TEMPLATE = """
    t{timestamp}: reserveParamsHistoryItems(
        first: 1
        where: {{reserve: $reserve, timestamp_gt: {timestamp}, timestamp_lt: {timestamp_end} }}
    ) {{
        liquidityRate
        priceInUsd
        timestamp
        __typename 
    }}"""

url = "https://api.thegraph.com/subgraphs/name/aave/protocol-v2"

start = datetime.datetime(2021, 1, 1, tzinfo=datetime.timezone.utc)
# start = datetime.datetime(2020, 7, 13, tzinfo=datetime.timezone.utc)
end = datetime.datetime(2021, 10, 1, tzinfo=datetime.timezone.utc)
delta = datetime.timedelta(days=1)
batch_size = 5


csv = open("rates.csv", "wt")
print("day,rate", file=csv)


cursor = start
while cursor < end:
    query_bits = []
    for i in range(batch_size):
        timestamp = int(cursor.timestamp())
        timestamp_end = int((cursor + delta).timestamp())
        query_bits.append(TEMPLATE.format(**locals()))
        cursor += delta

    q = """query ($reserve: String!) {"""
    for bit in query_bits:
        q += bit
    q += """}"""

    body = {
        "variables": {
            "reserve": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb480xb53c1a33016b2dc2ff3653530bff1848a515c8c5"
        },
        "query": q
    }

    resp = requests.post(url, json=body)
    assert resp.status_code == 200, f"Got status {resp.status_code}"
    out = resp.json()
    if "errors" in out:
        print(q)
        print(out)
        sys.exit()

    data = out["data"]

    for key, structure in data.items():
        timestamp = int(key[1:])
        day = datetime.datetime.utcfromtimestamp(timestamp)
        # print("Day ", day)
        # print(structure)

        lq = int(structure[0]["liquidityRate"])
        rate = lq / 10**27
        print(f"{day.isoformat()},{rate}", file=csv)



