from flask import Flask, request, jsonify, make_response, Response
import requests
import time
import uuid
from waitress import serve
import json
import tiktoken
import socket
from mistral_common.tokens.tokenizers.mistral import MistralTokenizer
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import os
import logging
from PIL import Image
from io import BytesIO
import coloredlogs
import printedcolors
import base64

# Create a logger object
logger = logging.getLogger(__name__)

# Install coloredlogs with desired log level
coloredlogs.install(level='DEBUG', logger=logger)




# Function to ensure the storage directory exists
def check_if_storage_folder_exists():
    if not os.path.exists("storage"):
        os.makedirs("storage")
        
print('''  _ __  __ _      ___     _           
 / |  \/  (_)_ _ | _ \___| |__ _ _  _ 
 | | |\/| | | ' \|   / -_) / _` | || |
 |_|_|  |_|_|_||_|_|_\___|_\__,_|\_, |
                                 |__/ ''')


def calculate_token(sentence, model="DEFAULT"):
    """Calculate the number of tokens in a sentence based on the specified model."""
    
    if model.startswith("mistral"):
        # Initialize the Mistral tokenizer
        tokenizer = MistralTokenizer.v3(is_tekken=True)
        tokens = tokenizer.encode(sentence)
        return len(tokens)

    elif model in ["gpt-3.5-turbo", "gpt-4"]:
        # Use OpenAI's tiktoken for GPT models
        encoding = tiktoken.encoding_for_model(model)
        tokens = encoding.encode(sentence)
        return len(tokens)

    else:
        # Default to openai
        encoding = tiktoken.encoding_for_model("gpt-4")
        tokens = encoding.encode(sentence)
        return len(tokens)
app = Flask(__name__)
try:
    limiter = Limiter(
        get_remote_address,
        app=app,
        storage_uri="memcached://memcached:11211",  # Connect to Memcached created with docker
    )
except:
    limiter = Limiter(
        get_remote_address,
        app=app,
    )
    logger.warning("Memcached is not available. Using in-memory storage for rate limiting. Not-Recommended")


ONE_MIN_API_URL = "https://api.1min.ai/api/features"
ONE_MIN_CONVERSATION_API_URL = "https://api.1min.ai/api/conversations"
ONE_MIN_CONVERSATION_API_STREAMING_URL = "https://api.1min.ai/api/features?isStreaming=true"
ONE_MIN_ASSET_URL = "https://api.1min.ai/api/assets"

ALL_ONE_MIN_AVAILABLE_MODELS = [
    "deepseek-chat",
    "o1-preview",
    "o1-mini",
    "gpt-4o-mini",
    "gpt-4o",
    "gpt-4-turbo",
    "gpt-4",
    "gpt-3.5-turbo",
    "claude-instant-1.2",
    "claude-2.1",
    "claude-3-5-sonnet-20240620",
    "claude-3-opus-20240229",
    "claude-3-sonnet-20240229",
    "claude-3-haiku-20240307",
    "gemini-1.0-pro",
    "gemini-1.5-pro",
    "gemini-1.5-flash",
    "mistral-large-latest",
    "mistral-small-latest",
    "mistral-nemo",
    "open-mistral-7b",

   # Replicate
   "meta/llama-2-70b-chat", 
   "meta/meta-llama-3-70b-instruct", 
   "meta/meta-llama-3.1-405b-instruct", 
   "command"
]

vision_supported_models = [
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4-turbo"
]


# Default values
SUBSET_OF_ONE_MIN_PERMITTED_MODELS = ["mistral-nemo", "gpt-4o", "deepseek-chat"]
PERMIT_MODELS_FROM_SUBSET_ONLY = False

# Read environment variables
one_min_models_env = os.getenv("SUBSET_OF_ONE_MIN_PERMITTED_MODELS")  # e.g. "mistral-nemo,gpt-4o,deepseek-chat"
permit_not_in_available_env = os.getenv("PERMIT_MODELS_FROM_SUBSET_ONLY")  # e.g. "True" or "False"

# Parse or fall back to defaults
if one_min_models_env:
    SUBSET_OF_ONE_MIN_PERMITTED_MODELS = one_min_models_env.split(",")


if permit_not_in_available_env and permit_not_in_available_env.lower() == "false":
    PERMIT_MODELS_FROM_SUBSET_ONLY = False

# EXTERNAL_AVAILABLE_MODELS, EXTERNAL_URL, etc. remain the same
EXTERNAL_AVAILABLE_MODELS = []
EXTERNAL_URL = "https://api.openai.com/v1/chat/completions"
EXTERNAL_API_KEY = ""

# Combine into a single list
AVAILABLE_MODELS = []
AVAILABLE_MODELS.extend(SUBSET_OF_ONE_MIN_PERMITTED_MODELS)
AVAILABLE_MODELS.extend(EXTERNAL_AVAILABLE_MODELS)

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        return ERROR_HANDLER(1212)
    if request.method == 'GET':
        internal_ip = socket.gethostbyname(socket.gethostname())
        return "Congratulations! Your API is working! You can now make requests to the API.\n\nEndpoint: " + internal_ip + ':5001/v1'
@app.route('/v1/models')
@limiter.limit("500 per minute")
def models():
    # Dynamically create the list of models with additional fields
    models_data = []
    if not PERMIT_MODELS_FROM_SUBSET_ONLY:
        one_min_models_data = [
            {
                "id": model_name,
                "object": "model",
                "owned_by": "1minai",
                "created": 1727389042,
                "capabilities": {"text": True, "vision": model_name in vision_supported_models}
            }
            for model_name in ALL_ONE_MIN_AVAILABLE_MODELS
        ]
    else:
        one_min_models_data = [
            {"id": model_name, "object": "model", "owned_by": "1minai", "created": 1727389042}
            for model_name in SUBSET_OF_ONE_MIN_PERMITTED_MODELS
        ]
    hugging_models_data = [
        {"id": model_name, "object": "model", "owned_by": "Hugging Face"}
        for model_name in EXTERNAL_AVAILABLE_MODELS
    ]
    models_data.extend(one_min_models_data)
    models_data.extend(hugging_models_data)
    return jsonify({"data": models_data, "object": "list"})

def create_convo(api):
    headers = {
        "API-KEY": api,
        "Content-Type": "application/json"
    }
    data = {
        "title": "New Managed Conversation",
        "type": "CHAT_WITH_AI",
    }
    response = requests.post(ONE_MIN_CONVERSATION_API_URL, headers=headers, data=json.dumps(data))
    return response.json()

def ERROR_HANDLER(code, model=None, key=None):
    error_codes = {
        1002: {"message": f"The model {model} does not exist.", "type": "invalid_request_error", "param": None, "code": "model_not_found", "http_code": 400},
        1020: {"message": f"Incorrect API key provided: {key}. You can find your API key at https://app.1min.ai/api.", "type": "authentication_error", "param": None, "code": "invalid_api_key", "http_code": 401},
        1212: {"message": f"Incorrect Endpoint. Please use the /v1/chat/completions endpoint.", "type": "invalid_request_error", "param": None, "code": "model_not_supported", "http_code": 400},
        1044: {"message": f"This model does not support image inputs."}
    }
    # Return the error in a openai format
    error_data = {k: v for k, v in error_codes.get(code, {"message": "Unknown error", "type": "unknown_error", "param": None, "code": None}).items() if k != "http_code"}
    logger.error(f"An error has occurred while processing the user's request. Error code: {code}")
    return jsonify({"error": error_data}), error_codes.get(code, {}).get("http_code", 400)

def format_conversation_history(messages, new_input):
    """
    Formats the conversation history into a structured string.
    
    Args:
        messages (list): List of message dictionaries from the request
    
    Returns:
        str: Formatted conversation history
    """
    formatted_history = ["Conversation History:\n"]
    for message in messages:
        role = message.get('role', '').capitalize()
        content = message.get('content', '')
        
        # Handle potential list content
        if isinstance(content, list):
            for item in content:
                if 'text' in item:
                    content = '\n'.join(item['text'])
                if 'image_url' in item:
                    print("Image URL")
        
        formatted_history.append(f"{role}: {content}")
    formatted_history.append("Respond like normal. The conversation history will be automatically updated on the next MESSAGE. DO NOT ADD User: or Assistant: to your output. Just respond like normal.")
    formatted_history.append("User Message:\n" + new_input)
    
    return '\n'.join(formatted_history)

@app.route('/v1/chat/completions', methods=['POST', 'OPTIONS'])
@limiter.limit("500 per minute")
def conversation():
    if request.method == 'OPTIONS':
        return handle_options_request()
    image = False
    

    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith("Bearer "):
        logger.error("Invalid Authentication")
        return jsonify({"error": {"message": "Invalid Authentication", "type": "invalid_request_error", "param": None, "code": None}}), 401
    
    api_key = auth_header.split(" ")[1]
    
    headers = {
        'API-KEY': api_key
    }
    
    request_data = request.json
    
    all_messages = format_conversation_history(request_data.get('messages', []), request_data.get('new_input', ''))

    messages = request_data.get('messages', [])
    if not messages:
        return jsonify({"error": {"message": "No messages provided", "type": "invalid_request_error", "param": "messages", "code": None}}), 400

    user_input = messages[-1].get('content')
    if not user_input:
        return jsonify({"error": {"message": "No content in the last message", "type": "invalid_request_error", "param": "messages", "code": None}}), 400

    # Check if user_input is a list and combine text if necessary
    image = False
    if isinstance(user_input, list):
        for item in user_input:
            if 'text' in item:
                combined_text = '\n'.join(item['text'])
            try:
                if 'image_url' in item:
                    if request_data.get('model', 'mistral-nemo') not in vision_supported_models:
                        return ERROR_HANDLER(1044, request_data.get('model', 'mistral-nemo'))
                    if item['image_url']['url'].startswith("data:image/png;base64,"):
                        base64_image = item['image_url']['url'].split(",")[1]
                        binary_data = base64.b64decode(base64_image)
                    else:
                        binary_data = requests.get(item['image_url']['url'])
                        binary_data.raise_for_status()  # Raise an error for bad responses
                        binary_data = BytesIO(binary_data.content)
                    files = {
                        'asset': ("relay" + str(uuid.uuid4()), binary_data, 'image/png')
                    }
                    asset = requests.post(ONE_MIN_ASSET_URL, files=files, headers=headers)
                    asset.raise_for_status()  # Raise an error for bad responses
                    image_path = asset.json()['fileContent']['path']
                    image = True
                    print("Image URL")
            except Exception as e:
                print(f"An error occurred e:" + str(e)[:60])
                # Optionally log the error or return an appropriate response

        user_input = str(combined_text)

    prompt_token = calculate_token(str(all_messages))
    if PERMIT_MODELS_FROM_SUBSET_ONLY and request_data.get('model', 'mistral-nemo') not in AVAILABLE_MODELS:
        return ERROR_HANDLER(1002, request_data.get('model', 'mistral-nemo'))
    
    logger.debug(f"Proccessing {prompt_token} prompt tokens with model {request_data.get('model', 'mistral-nemo')}")

    if not image:
        payload = {
            "type": "CHAT_WITH_AI",
            "model": request_data.get('model', 'mistral-nemo'),
            "promptObject": {
                "prompt": all_messages,
                "isMixed": False,
                "webSearch": False
            }
        }
    else:
        payload = {
            "type": "CHAT_WITH_IMAGE",
            "model": request_data.get('model', 'mistral-nemo'),
            "promptObject": {
                "prompt": all_messages,
                "isMixed": False,
                "imageList": [image_path]
            }
        }
    
    headers = {"API-KEY": api_key, 'Content-Type': 'application/json'}

    if not request_data.get('stream', False):
        logger.debug("Non-Streaming AI Response")
        response = requests.post(ONE_MIN_API_URL, json=payload, headers=headers)
        print(response.text)
        response.raise_for_status()
        one_min_response = response.json()
        
        transformed_response = transform_response(one_min_response, request_data, prompt_token)
        response = make_response(jsonify(transformed_response))
        set_response_headers(response)
        
        return response, 200
    
    else:
        logger.debug("Streaming AI Response")
        response_stream = requests.post(ONE_MIN_CONVERSATION_API_STREAMING_URL, data=json.dumps(payload), headers=headers, stream=True)
        if response_stream.status_code != 200:
            if response_stream.status_code == 401:
                return ERROR_HANDLER(1020)
            logger.error(f"An unknown error occurred while processing the user's request. Error code: {response_stream.status_code}")
            return ERROR_HANDLER(response_stream.status_code)
        return Response(actual_stream_response(response_stream, request_data, request_data.get('model', 'mistral-nemo'), int(prompt_token)), content_type='text/event-stream')
def handle_options_request():
    response = make_response()
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
    return response, 204

def transform_response(one_min_response, request_data, prompt_token):
    completion_token = calculate_token(one_min_response['aiRecord']["aiRecordDetail"]["resultObject"][0])
    return {
        "id": f"chatcmpl-{uuid.uuid4()}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": request_data.get('model', 'mistral-nemo'),
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": one_min_response['aiRecord']["aiRecordDetail"]["resultObject"][0],
                },
                "finish_reason": "stop"
            }
        ],
        "usage": {
            "prompt_tokens": prompt_token,
            "completion_tokens": completion_token,
            "total_tokens": prompt_token + completion_token
        }
    }
    
def set_response_headers(response ):
    response.headers['Content-Type'] = 'application/json'
    response.headers['Access -Control-Allow-Origin'] = '*'
    response.headers['X-Request-ID'] = str (uuid.uuid4())

def stream_response(content, request_data):
    words = content.split()
    for i, word in enumerate(words):
        chunk = {
            "id": f"chatcmpl-{uuid.uuid4()}",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": request_data.get('model', 'mistral-nemo'),
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "content": word + " "
                    },
                    "finish_reason": None if i < len(words) - 1 else "stop"
                }
            ]
        }
        yield f"data: {json.dumps(chunk)}\n\n"
        time.sleep(0.05)
    yield "data: [DONE]\n\n"

def actual_stream_response(response, request_data, model, prompt_tokens):
    all_chunks = ""
    for chunk in response.iter_content(chunk_size=1024):
        finish_reason = None

        return_chunk = {
            "id": f"chatcmpl-{uuid.uuid4()}",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": request_data.get('model', 'mistral-nemo'),
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "content": chunk.decode('utf-8')
                    },
                    "finish_reason": finish_reason
                }
            ]
        }
        all_chunks += chunk.decode('utf-8')
        yield f"data: {json.dumps(return_chunk)}\n\n"
        
    tokens = calculate_token(all_chunks)
    logger.debug(f"Finished processing response. Completion tokens: {str(tokens)}")
    logger.debug(f"Total tokens: {str(tokens + prompt_tokens)}")
        
    # Final chunk when iteration stops
    final_chunk = {
        "id": f"chatcmpl-{uuid.uuid4()}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": request_data.get('model', 'mistral-nemo'),
        "choices": [
            {
                "index": 0,
                "delta": {
                    "content": ""    
                },
                "finish_reason": "stop"
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": tokens,
            "total_tokens": tokens + prompt_tokens
        }
    }
    yield f"data: {json.dumps(final_chunk)}\n\n"
    yield "data: [DONE]\n\n"

if __name__ == '__main__':
    internal_ip = socket.gethostbyname(socket.gethostname())
    print(printedcolors.Color.fg.lightcyan)
    print('\n\nServer is ready to serve at:')
    print('Internal IP: ' + internal_ip + ':5001')
    print('\nEnter this url to OpenAI clients supporting custom endpoint:')
    print(internal_ip + ':5001/v1')
    print('If does not work, try:')
    print(internal_ip + ':5001/v1/chat/completions')
    print(printedcolors.Color.reset)
    serve(app, host='0.0.0.0', port=5001, threads=6)
