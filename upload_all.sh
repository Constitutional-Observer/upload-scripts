#!/bin/bash

python3 update_embeddings.py --meilisearch-url http://localhost:7700 --index state_legislature_debates_ap --meilisearch-key xyz
python3 update_embeddings.py --meilisearch-url http://localhost:7700 --index state_legislature_debates_as --meilisearch-key xyz
python3 update_embeddings.py --meilisearch-url http://localhost:7700 --index state_legislature_debates_ka --meilisearch-key xyz
python3 update_embeddings.py --meilisearch-url http://localhost:7700 --index state_legislature_debates_kl --meilisearch-key xyz
python3 update_embeddings.py --meilisearch-url http://localhost:7700 --index state_legislature_debates_rj --meilisearch-key xyz
python3 update_embeddings.py --meilisearch-url http://localhost:7700 --index state_legislature_debates_tg --meilisearch-key xyz
python3 update_embeddings.py --meilisearch-url http://localhost:7700 --index state_legislature_debates_tn --meilisearch-key xyz
python3 update_embeddings.py --meilisearch-url http://localhost:7700 --index state_legislature_debates_up --meilisearch-key xyz
python3 update_embeddings.py --meilisearch-url http://localhost:7700 --index state_legislature_debates_wb --meilisearch-key xyz

python upload_meilisearch.py --host http://localhost:7700 --api-key xyz ../../ia-txt/AP
python upload_meilisearch.py --host http://localhost:7700 --api-key xyz ../../ia-txt/AS
python upload_meilisearch.py --host http://localhost:7700 --api-key xyz ../../ia-txt/KA
python upload_meilisearch.py --host http://localhost:7700 --api-key xyz ../../ia-txt/KL
python upload_meilisearch.py --host http://localhost:7700 --api-key xyz ../../ia-txt/RJ
python upload_meilisearch.py --host http://localhost:7700 --api-key xyz ../../ia-txt/TG
python upload_meilisearch.py --host http://localhost:7700 --api-key xyz ../../ia-txt/TN
python upload_meilisearch.py --host http://localhost:7700 --api-key xyz ../../ia-txt/UP
python upload_meilisearch.py --host http://localhost:7700 --api-key xyz ../../ia-txt/WB
