import json
import os
import requests
import time
from dotenv import load_dotenv
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
import openai
from openai import OpenAI
from flask import Flask, render_template, request, send_from_directory
from tenacity import retry, stop_after_attempt, wait_random_exponential
import re

# Load environment variables
load_dotenv()

# Initialize OpenAI client with API key
#openai.api.key = os.getenv('OPENAI_API_KEY')
# Load SendGrid API Key from environment
SENDGRID_API_KEY = os.getenv('SENDGRID_API_KEY')
# OpenAI model - gpt-4o-mini is the cheapest
GPT_MODEL = "gpt-4o-mini"

client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

# Flask app setup
app = Flask(__name__)

@app.route('/images/<path:filename>')
def images(filename):
    return send_from_directory('images', filename)

@app.route('/css/<path:filename>')
def css(filename):
    return send_from_directory('css', filename)

#***********************************
# User define functions
#***********************************
# Function to send email
def send_email(to, subject, body):
    """
    Sends an email using SendGrid API.

    Args:
        to (str): Recipient's email address.
        subject (str): Subject of the email.
        body (str): Email body content.

    Returns:
        str: "success" if the email is sent successfully, otherwise "error".
    """
    SENDER = "van.lam@cstu.edu"  # Replace with verified sender email

    # HTML email body with proper formatting
    BODY_HTML = f"""
    <html>
    <head>
        <style>
            body {{
                font-family: Arial, sans-serif;
                line-height: 1.6;
                color: #333;
            }}
            .email-container {{
                max-width: 600px;
                margin: 0 auto;
                padding: 20px;
                border: 1px solid #ddd;
                border-radius: 10px;
                background-color: #f9f9f9;
            }}
            .email-header {{
                font-size: 24px;
                color: #4CAF50;
                margin-bottom: 20px;
            }}
            .email-content {{
                font-size: 16px;
                color: #555;
            }}
            .email-footer {{
                margin-top: 20px;
                font-size: 14px;
                color: #777;
            }}
        </style>
    </head>
    <body>
        <div class="email-container">
            <div class="email-header">Requested Information</div>
            <div class="email-content">
                This email was sent by DisasterConnect Chatbot.
                <br><br>
                You have requested the following information:
                <br><br>
                {process_text_message_content(body)}
            </div>
            <div class="email-footer">
                Thank you for using DisasterConnect. Stay safe!
            </div>
        </div>
    </body>
    </html>
    """

    try:
        # Create and send the email
        message = Mail(
            from_email=SENDER,
            to_emails=to,
            subject=subject,
            html_content=BODY_HTML
        )
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(message)

        if response.status_code in (200, 202):
            print(f"Email sent! Status Code: {response.status_code}")
            return "success"
        else:
            print(f"Failed to send email. Status Code: {response.status_code}")
            return "error"

    except Exception as e:
        print(f"An error occurred: {e}")
        return "error"
    

def get_current_weather(latitude, longitude):
    """
    Fetches the current weather for a given latitude and longitude using the Open-Meteo API.

    Args:
        latitude (float): Latitude of the location.
        longitude (float): Longitude of the location.

    Returns:
        dict: Weather data including temperature in Celsius and Fahrenheit, wind speed, and humidity.
    """
    try:
        # Open-Meteo API endpoint with required parameters
        url = f"https://api.open-meteo.com/v1/forecast?latitude={latitude}&longitude={longitude}&current_weather=true"
        
        # Make the GET request
        response = requests.get(url)
        response.raise_for_status()  # Raise an exception for HTTP errors
        
        # Parse the JSON response
        data = response.json()
        
        # Extract relevant weather information
        if "current_weather" in data:
            current_weather = data["current_weather"]
            temperature_C = current_weather["temperature"]
            temperature_F = temperature_C * 9/5 + 32  # Convert Celsius to Fahrenheit
            return {
                "temperature_C": temperature_C,
                "temperature_F": temperature_F,
                "wind_speed_mph": current_weather["windspeed"] * 0.621371,  # Convert km/h to mph
                "humidity": current_weather.get("humidity", "N/A"),  # Include if available
                "latitude": latitude,
                "longitude": longitude,
            }
        else:
            return {"error": "Current weather data not available"}
    except requests.RequestException as e:
        return {"error": f"Failed to fetch weather data: {str(e)}"}
    except KeyError:
        return {"error": "Unexpected response format"}
    
def get_shelter_info(latitude, longitude, radius=50000, limit=10):
    """
    Fetches real-time shelter information near a given latitude and longitude using the American Red Cross Shelter API.

    Args:
        latitude (float): Latitude of the location.
        longitude (float): Longitude of the location.
        radius (int): Search radius in meters (default is 50000 meters or 50 km).
        limit (int): Maximum number of results to return (default is 10).

    Returns:
        dict: Information about nearby shelters, including location, capacity, and status.
    """
    try:
        # American Red Cross Shelter API endpoint (example URL, replace with actual API endpoint)
        url = "https://api.redcross.org/shelters"
        
        # Query parameters
        params = {
            "lat": latitude,
            "lon": longitude,
            "radius": radius,
            "limit": limit
        }
        
        # Make the GET request
        response = requests.get(url, params=params)
        response.raise_for_status()  # Raise an exception for HTTP errors
        
        # Parse the JSON response
        data = response.json()
        
        # Extract relevant information about shelters
        shelters = []
        for shelter in data.get("shelters", []):
            shelters.append({
                "shelter_id": shelter.get("id"),
                "name": shelter.get("name"),
                "address": shelter.get("address"),
                "city": shelter.get("city"),
                "state": shelter.get("state"),
                "postal_code": shelter.get("postal_code"),
                "latitude": shelter.get("latitude"),
                "longitude": shelter.get("longitude"),
                "capacity": shelter.get("capacity"),
                "current_occupancy": shelter.get("current_occupancy"),
                "status": shelter.get("status"),  # e.g., "open", "closed", "full"
            })
        
        return {
            "latitude": latitude,
            "longitude": longitude,
            "radius_meters": radius,
            "shelters": shelters,
        }
    except requests.RequestException as e:
        return {"error": f"Failed to fetch shelter data: {str(e)}"}
    except KeyError:
        return {"error": "Unexpected response format"}

# Setup the tools and include user defined functions
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_current_weather",
            "description": "Get the current weather using latitude and longitude",
            "parameters": {
                "type": "object",
                "properties": {
                    "latitude": {
                        "type": "number",
                        "description": "The latitude of the location, e.g., 37.7749",
                    },
                    "longitude": {
                        "type": "number",
                        "description": "The longitude of the location, e.g., -122.4194",
                    }
                },
                "required": ["latitude", "longitude"],
                "additionalProperties": False
            },
            "strict": True
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_email",
            "description": "Send an email as confirmation email to student.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {
                        "type": "string",
                        "description": "the recipient email address",
                    },
                    "subject": {
                        "type": "string",
                        "description": "the subject of the email",
                    },
                    "body": {
                        "type": "string",
                        "description": "the body of the email",
                    },

                },
                "required": ["to", "subject", "body"],
                "additionalProperties": False
            },
            "strict": True
        }
    }, 
    {
        "type": "function",
        "function": {
            "name": "get_shelter_info",
            "description": "Get real-time information about shelters near a given latitude and longitude",
            "parameters": {
                "type": "object",
                "properties": {
                    "latitude": {
                        "type": "number",
                        "description": "The latitude of the location, e.g., 37.7749",
                    },
                    "longitude": {
                        "type": "number",
                        "description": "The longitude of the location, e.g., -122.4194",
                    },
                    "radius": {
                        "type": "integer",
                        "description": "The search radius in meters, e.g., 50000",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "The maximum number of results to return, e.g., 10",
                    }
                },
                "required": ["latitude", "longitude"],  # Only latitude and longitude are required
                "additionalProperties": False
            },
            "strict": False
        }
    },
]

available_functions = {
    "get_current_weather": get_current_weather,
    "send_email": send_email,
    "get_shelter_info": get_shelter_info,
}
#***********************************
# Helper functions
#***********************************
def process_message_content(content):
    """Process message content to convert various image references to HTML"""
    # Pattern for explicit image tags
    pattern1 = r'<image>(.*?)</image>'
    
    # Pattern for Markdown image syntax
    pattern2 = r'!\[(.*?)\]\((images/[^)]+)\)'
    
    # Pattern for parenthetical image references
    pattern3 = r'\(images/([^)]+)\)'
    
    # Replace explicit image tags
    processed_content = re.sub(
        pattern1, 
        r'<img src="/images/\1" alt="Resource Image" class="chat-image" />', 
        content
    )
    
    # Replace Markdown image syntax
    processed_content = re.sub(
        pattern2,
        r'<img src="/images/\2" alt="\1" class="chat-image" />',
        processed_content
    )
    
    # Replace parenthetical image references
    processed_content = re.sub(
        pattern3, 
        r'<img src="/images/\1" alt="Resource Image" class="chat-image" />', 
        processed_content
    )
    
    return processed_content

def process_text_message_content(response_message_content):
    # Format the response with proper HTML and spacing
        formatted_response = response_message_content.replace("\n", "<br>")
        
        # Add proper spacing and formatting for sections
        formatted_response = re.sub(r'###\s*(.*?):', r'<br><br><strong>\1:</strong><br>', formatted_response)
        
        # Format numbered lists with proper spacing and indentation
        formatted_response = re.sub(
            r'(\d+\.\s+\*\*.*?\*\*)',
            r'<br>\1',
            formatted_response
        )
        
        # Format bullet points with proper spacing and indentation
        formatted_response = re.sub(
            r'-\s+\*\*([^*]+)\*\*:',
            r'<br>&emsp;• <strong>\1:</strong>',
            formatted_response
        )
        
        # Format regular bullet points
        formatted_response = re.sub(
            r'-\s+([^<])',
            r'<br>&emsp;• \1',
            formatted_response
        )
        
        # Convert markdown bold to HTML
        formatted_response = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', formatted_response)
        
        return formatted_response
    

def get_addition_resources(file):
    with open(file, 'r', encoding='utf-8') as file:
            # Read the entire contents of the file into a variable
            file_content = file.read()
    return file_content

additional_resources = get_addition_resources('data/additional_resources.txt')
survivor_resources = get_addition_resources('data/user_type_resources/survivor.txt')
provider_resources = get_addition_resources('data/user_type_resources/provider.txt')
public_resources = get_addition_resources('data/user_type_resources/concerned_public.txt')
relief_org_resources = get_addition_resources('data/user_type_resources/relief_organiztion.txt')

chatContext = [
    {'role': 'developer', 'content': f"""
Objective: You are a smart, friendly virtual assistant tasked with assisting individuals affected by disasters, with context-aware responses based on the user's type.

User Types:
1. Survivor/Caregiver: Prioritize immediate relief, safety information, and support resources
2. Provider/Donater: Focus on donation channels, resource allocation, and ways to help
3. Concerned Public: Provide general information, updates, and guidance
4. Relief Organizer: Offer coordination resources, emergency contact information, and strategic support

Procedure:
1. Tailor responses based on the selected user type
2. Provide specific, relevant information and resources
3. Maintain a supportive and informative tone
{additional_resources}

{survivor_resources}

{provider_resources}

{public_resources}

{relief_org_resources}
"""
    },
]

# Store conversation history (global variable for simplicity)
chat_history = []

@retry(wait=wait_random_exponential(multiplier=1, max=40), stop=stop_after_attempt(3))
def chat_completion_request(messages, temperature=0, tools=None, tool_choice=None, model=GPT_MODEL):
    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            tools=tools,
            tool_choice=tool_choice,
        )
        return response
    except Exception as e:
        print("Unable to generate ChatCompletion response")
        print(f"Exception: {e}")
        return e
    
def chat_complete_messages(messages, temperature=0):
    try:
        response = client.chat.completions.create(
            model=GPT_MODEL,
            messages=messages,
            temperature=temperature,
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error with OpenAI API: {e}")
        return "Sorry, there was an issue processing your request."

def get_initial_greeting():
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    try:
        # Get bot's initial greeting
        greeting = chat_complete_messages([
            {'role': 'system', 'content': chatContext[0]['content']},
            {'role': 'user', 'content': 'Provide a compassionate and informative initial greeting for a disaster relief chatbot.'}
        ], 0)
        
        # Append user type selection prompt to the greeting with better formatting
        user_type_prompt = """
        <br><br>
        To best assist you, could you please tell me your role in this disaster situation?
        <br><br>
        Are you:
        <br>
        &emsp;1. A Survivor/Caregiver
        <br>
        &emsp;2. A Provider/Donor
        <br>
        &emsp;3. Concerned Public
        <br>
        &emsp;4. A Relief Organization
        <br><br>
        Please respond with the number that corresponds to your role.
        """
        
        full_greeting = greeting + user_type_prompt
        
        # Add greeting to chat history and context
        chat_history.append((full_greeting, "bot", timestamp))
        chatContext.append({'role': 'assistant', 'content': full_greeting})
        
        return full_greeting
    except Exception as e:
        print(f"Error getting initial greeting: {e}")
        error_message = """
        Welcome to DisasterConnect. We're here to help during this challenging time.
        <br><br>
        To best assist you, could you please tell me your role in this disaster situation?
        <br><br>
        Are you:
        <br>
        &emsp;1. A Survivor/Caregiver
        <br>
        &emsp;2. A Provider/Donor
        <br>
        &emsp;3. Concerned Public
        <br>
        &emsp;4. A Relief Organization
        <br><br>
        Please respond with the number that corresponds to your role.
        """
        chat_history.append((error_message, "bot", timestamp))
        return error_message
    
def get_disaster_relief_response(user_input):
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    
    # Add user message to chat history and context
    chat_history.append((user_input, "user", timestamp))
    chatContext.append({'role': 'user', 'content': user_input})

    try:
        # Get bot response
        response_message = chat_completion_request(chatContext, temperature=0, tools=tools, tool_choice="auto")
        assistant_message = response_message.choices[0].message
        response_message_content = assistant_message.content
        
        tool_calls = assistant_message.tool_calls
        
        if tool_calls:
            # Step 3: call the function.
            chatContext.append(assistant_message)  # extend conversation with assistant's reply

            # Step 4: send the info for each function call and function response to the model
            for tool_call in tool_calls:
                function_name = tool_call.function.name
                print("GPT to call! function: ", function_name)
                function_to_call = available_functions[function_name]
                function_args = json.loads(tool_call.function.arguments)

                function_response = function_to_call(**function_args)  # argument unpacking

                email_status = function_response

                print(f"ChatBot: Oh, just found the email sending status is {email_status}")

                # Convert the function_response (dictionary) to a string
                function_response_str = json.dumps(function_response)

                chatContext.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": function_response_str,  # Use the stringified response
                    }
                )
                response_message = chat_completion_request(chatContext, temperature=0, tools=tools, tool_choice="auto")
                response_message_content = response_message.choices[0].message.content

        # Format the response with proper HTML and spacing
        formatted_response = response_message_content.replace("\n", "<br>")
        
        # Add proper spacing and formatting for sections
        formatted_response = re.sub(r'###\s*(.*?):', r'<br><br><strong>\1:</strong><br>', formatted_response)
        
        # Format numbered lists with proper spacing and indentation
        formatted_response = re.sub(
            r'(\d+\.\s+\*\*.*?\*\*)',
            r'<br>\1',
            formatted_response
        )
        
        # Format bullet points with proper spacing and indentation
        formatted_response = re.sub(
            r'-\s+\*\*([^*]+)\*\*:',
            r'<br>&emsp;• <strong>\1:</strong>',
            formatted_response
        )
        
        # Format regular bullet points
        formatted_response = re.sub(
            r'-\s+([^<])',
            r'<br>&emsp;• \1',
            formatted_response
        )
        
        # Convert markdown bold to HTML
        formatted_response = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', formatted_response)
        
        # Process any image tags
        processed_response = process_message_content(formatted_response)
        
        chatContext.append({'role': 'assistant', 'content': f"{response_message_content}"})
        chat_history.append((processed_response, "bot", timestamp))
        
        return processed_response
        
    except Exception as e:
        print(f"Error processing response: {e}")
        return f"I apologize, but I encountered an error while processing your request. Please try again."
      
    
def process_user_type_selection(user_input):
    """Process user type selection and generate appropriate response"""
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    
    # Add user message to chat history and context
    chat_history.append((user_input, "user", timestamp))
    chatContext.append({'role': 'user', 'content': user_input})
    
    user_type_map = {
        '1': 'Survivor/Caregiver',
        '2': 'Provider/Donor',
        '3': 'Concerned Public',
        '4': 'Relief Organization'
    }
    
    # Validate user input
    if user_input not in user_type_map:
        # If invalid input, ask again with proper formatting
        error_message = """
        I'm sorry, but I didn't understand your selection. 
        <br><br>
        Please respond with the number (1-4) that corresponds to your role:
        <br>
        &emsp;1. Survivor/Caregiver
        <br>
        &emsp;2. Provider/Donor
        <br>
        &emsp;3. Concerned Public
        <br>
        &emsp;4. Relief Organization
        """
        chat_history.append((error_message, "bot", timestamp))
        return error_message
    
    # Get the selected user type
    user_type = user_type_map[user_input]
    
    # Generate context-specific guidance
    try:
        user_type_guidance = chat_complete_messages([{
            'role': 'system', 'content': f"""
            You are a disaster relief chatbot. Provide specific, compassionate guidance for a {user_type} in a disaster situation.
            
            Context guidance:
            - Survivors/Caregivers: Focus on immediate needs, safety, and support resources
            - Providers/Donors: Explain ways to provide meaningful assistance
            - Concerned Public: Offer accurate, up-to-date information and ways to stay informed
            - Relief Organizations: Provide coordination resources and strategic support
            """
        }, {
            'role': 'user', 'content': f'Generate a detailed, supportive initial guidance for a {user_type} during a disaster relief effort.'
        }], 0)

        # Apply the same formatting logic as in get_disaster_relief_response
        formatted_response = user_type_guidance.replace("\n", "<br>")
        
        # Add proper spacing and formatting for sections
        formatted_response = re.sub(r'###\s*(.*?):', r'<br><br><strong>\1:</strong><br>', formatted_response)
        
        # Format numbered lists with proper spacing and indentation
        formatted_response = re.sub(
            r'(\d+\.\s+\*\*.*?\*\*)',
            r'<br>\1',
            formatted_response
        )
        
        # Format bullet points with proper spacing and indentation
        formatted_response = re.sub(
            r'-\s+\*\*([^*]+)\*\*:',
            r'<br>&emsp;• <strong>\1:</strong>',
            formatted_response
        )
        
        # Format regular bullet points
        formatted_response = re.sub(
            r'-\s+([^<])',
            r'<br>&emsp;• \1',
            formatted_response
        )
        
        # Convert markdown bold to HTML
        formatted_response = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', formatted_response)
        
        # Process any image tags
        processed_response = process_message_content(formatted_response)
        
        # Append to chat history
        chat_history.append((processed_response, "bot", timestamp))
        
        # Update context to reflect user type
        chatContext.append({
            'role': 'system', 
            'content': f'The user is identified as a {user_type}. Tailor all subsequent responses to their specific needs and context.'
        })
        
        return processed_response
    except Exception as e:
        print(f"Error processing user type: {e}")
        fallback_message = f"""
        Thank you for identifying yourself as a {user_type}. 
        <br><br>
        We're here to provide personalized support during this challenging time. 
        <br>
        What specific assistance do you need right now?
        """
        chat_history.append((fallback_message, "bot", timestamp))
        return fallback_message
    
@app.route("/", methods=["GET", "POST"])
def index():
    # Send initial greeting if chat history is empty
    if not chat_history:
        get_initial_greeting()

    if request.method == "POST":
        user_input = request.form["user_input"]
        
        # Check if this is a user type selection
        if chat_history and "tell me your role" in chat_history[-1][0].lower():
            response = process_user_type_selection(user_input)
        else:
            # Regular message processing
            response = get_disaster_relief_response(user_input)
        
        # If it's an AJAX request, return the full page
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return render_template("index.html", chat_history=chat_history)

    # Render the chat interface and pass the history to the template
    return render_template("index.html", chat_history=chat_history)

if __name__ == "__main__":
    app.run(debug=True)