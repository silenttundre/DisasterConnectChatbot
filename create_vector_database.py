import openai
from openai import OpenAI
import json
from pinecone.grpc import PineconeGRPC as Pinecone
from pinecone import ServerlessSpec

import time
import os
from dotenv import load_dotenv
load_dotenv()

# Assign pinecone PINECONE_API_KEY
pinecone_api_key = os.getenv("PINECONE_API_KEY")
#print(pinecone_api_key)

client = OpenAI()
pc = Pinecone(api_key=pinecone_api_key)
# Create your own vector database index name
index_name = 'cstugpt-dc'
embed_model = "text-embedding-3-small"


def pinecone_create_vector_database(index_name):
    try:
        # Get the list of existing indexes
        existing_indexes = pc.list_indexes()
        
        # If the index doesn't exist, create it
        if index_name not in existing_indexes:
            pc.create_index(
                name=index_name,
                dimension=1536,
                metric="cosine",
                spec=ServerlessSpec(
                    cloud='aws', 
                    region='us-east-1'
                ) 
            )
        
        # Wait for the index to be ready
        while not pc.describe_index(index_name).status['ready']:
            time.sleep(1)
    
    except Exception as e:
        # Handle general exceptions (like "ALREADY_EXISTS")
        if 'already exists' in str(e).lower():
            print(f"Index {index_name} already exists. Skipping creation.")
        else:
            print(f"An error occurred: {e}")
            raise

pinecone_create_vector_database(index_name)

def read_and_chunk_file(file_path, chunk_size=500):
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            text = file.read()
        
        # Split the text into chunks of `chunk_size` characters
        chunks = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]
        return chunks
    
    except UnicodeDecodeError as e:
        print(f"Error decoding the file {file_path}. Please check the file encoding.")
        raise

def pinecone_upsert_chunk(text, rec_count, index_name, namespace):
    index = pc.Index(index_name)
    res = client.embeddings.create(input=text, model=embed_model)

    embed = res.data[0].embedding
    print("Embeds length:", len(embed))
    
    count = rec_count
    # Meta data preparation
    metadata = {'text': text}
    
    index.upsert(vectors=[{"id": namespace + '_' + str(count), "metadata": metadata, "values": embed}], 
                 namespace=namespace)

# Read and chunk the file
file_path = 'data/additional_resources.txt'
chunks = read_and_chunk_file(file_path)

# Upsert each chunk into Pinecone
namespace = 'dc'
for i, chunk in enumerate(chunks):
    pinecone_upsert_chunk(chunk, i + 1, index_name, namespace)