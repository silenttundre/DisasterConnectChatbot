import json
import os
import requests
import time
import datetime
from dotenv import load_dotenv
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
import openai
from openai import OpenAI
from flask import Flask, render_template, request, send_from_directory
from tenacity import retry, stop_after_attempt, wait_random_exponential
import re
from pydantic import BaseModel, Field
from typing import Literal

class GetCurrentAirQuality(BaseModel):
    latitude: float = Field(..., description="The latitude of the location, e.g., 37.7749")
    longitude: float = Field(..., description="The longitude of the location, e.g., -122.4194")
    
# Load environment variables
load_dotenv()

# Initialize OpenAI client with API key
#openai.api.key = os.getenv('OPENAI_API_KEY')
# Load SendGrid API Key from environment
SENDGRID_API_KEY = os.getenv('SENDGRID_API_KEY')
# OpenAI model - gpt-4o-mini is the cheapest
GPT_MODEL = "gpt-4o-mini"

CHATBOT_NAME = "DisasterConnect"

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
                This email was sent by {CHATBOT_NAME} Chatbot.
                <br><br>
                You have requested the following information:
                <br><br>
                {process_text_message_content(body)}
            </div>
            <div class="email-footer">
                Thank you for using {CHATBOT_NAME}. Stay safe!
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
            subject=CHATBOT_NAME + ": " + subject,
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
    Fetches shelter-related information near a given latitude and longitude using FEMA's Open API data.

    Args:
        latitude (float): Latitude of the location.
        longitude (float): Longitude of the location.
        radius (int): Search radius in meters (default is 50000 meters or 50 km).
        limit (int): Maximum number of results to return (default is 10).

    Returns:
        dict: Information about nearby shelters, including location, capacity, and disaster type.
    """
    try:
        # Step 1: Fetch disaster-related data from FEMA's Open API
        fema_url = "https://www.fema.gov/api/open/v2/DisasterDeclarationsSummaries"
        fema_params = {
            "api_key": "YOUR_FEMA_API_KEY",  # Replace with your actual API key
            "latitude": latitude,
            "longitude": longitude,
            "radius": radius
        }

        fema_response = requests.get(fema_url, params=fema_params)
        fema_response.raise_for_status()

        # Parse FEMA response
        fema_data = fema_response.json()

        # Step 2: Process FEMA disaster-related data
        shelters = []

        for disaster in fema_data.get("data", []):
            # Filter for disaster types that generally require shelters
            disaster_info = {
                "disaster_id": disaster.get("disasterNumber"),
                "disaster_name": disaster.get("incidentType"),
                "disaster_state": disaster.get("state"),
                "disaster_date": disaster.get("declarationDate"),
                "incident_begin_date": disaster.get("incidentBeginDate"),
                "incident_end_date": disaster.get("incidentEndDate"),
                "shelter_needed": disaster.get("incidentType") in ["Hurricane", "Flood", "Tornado", "Wildfire"],  # Example filter
                "affected_area": disaster.get("incidentBeginDate")
            }

            shelters.append(disaster_info)

        return {
            "latitude": latitude,
            "longitude": longitude,
            "radius_meters": radius,
            "shelters": shelters[:limit],  # Limit results to the specified limit
        }
        
    except requests.RequestException as e:
        return {"error": f"Failed to fetch shelter or disaster data: {str(e)}"}
    except KeyError:
        return {"error": "Unexpected response format"}

def get_current_airquality(latitude, longitude, date, distance = 25, format = 'application/json'):
    """
    Fetches the current air quality for a given latitude and longitude using the AirNow API.

    Args:
        format(string): application/json, text/csv, application/xml (output format) 
        latitude (float): Latitude of the location.
        longitude (float): Longitude of the location.
        date(string): query date(eg. 2025-1-28)
        distance(string): query distance radius(eg. 25)

    Returns:
        application/jason: [{"DateIssue":"2025-01-28","DateForecast":"2025-01-28","ReportingArea":"Yuba City and Marysville",
        "StateCode":"CA","Latitude":39.1389,"Longitude":-121.6175,"ParameterName":"PM2.5","AQI":77,
        "Category":{"Number":2,"Name":"Moderate"},
        "ActionDay":false,"Discussion":""},{"DateIssue":"2025-01-28","DateForecast":"2025-01-29",
        "ReportingArea":"Yuba City and Marysville","StateCode":"CA","Latitude":39.1389,"Longitude":-121.6175,
        "ParameterName":"PM2.5","AQI":77,"Category":{"Number":2,"Name":"Moderate"},"ActionDay":false,"Discussion":""}]

        text/csv: "DateIssue","DateForecast","ReportingArea","StateCode","Latitude","Longitude","ParameterName","AQI",
        "CategoryNumber","CategoryName","ActionDay","Discussion"
        "2025-01-28","2025-01-28","Yuba City and Marysville","CA","39.1389","-121.6175","PM2.5","77","2","Moderate","false",""
        "2025-01-28","2025-01-29","Yuba City and Marysville","CA","39.1389","-121.6175","PM2.5","77","2","Moderate","false",""

        application/xml: <ForecastByLatLonList>
  <ForecastByLatLon>
    <DateIssue>01/28/2025 12:00:00 AM</DateIssue>
    <DateForecast>01/28/2025 12:00:00 AM</DateForecast>
    <ReportingArea>Yuba City and Marysville</ReportingArea>
    <StateCode>CA</StateCode>
    <Latitude>39.1389</Latitude>
    <Longitude>-121.6175</Longitude>
    <ParameterName>PM2.5</ParameterName>
    <AQI>77</AQI>
    <CategoryNumber>2</CategoryNumber>
    <CategoryName>Moderate</CategoryName>
    <ActionDay>False</ActionDay>
    <Discussion></Discussion>
  </ForecastByLatLon>
  <ForecastByLatLon>
    <DateIssue>01/28/2025 12:00:00 AM</DateIssue>
    <DateForecast>01/29/2025 12:00:00 AM</DateForecast>
    <ReportingArea>Yuba City and Marysville</ReportingArea>
    <StateCode>CA</StateCode>
    <Latitude>39.1389</Latitude>
    <Longitude>-121.6175</Longitude>
    <ParameterName>PM2.5</ParameterName>
    <AQI>77</AQI>
    <CategoryNumber>2</CategoryNumber>
    <CategoryName>Moderate</CategoryName>
    <ActionDay>False</ActionDay>
    <Discussion></Discussion>
  </ForecastByLatLon>
</ForecastByLatLonList>
    """
    try:
        # Open-Meteo API endpoint with required parameters
        url = f"https://www.airnowapi.org/aq/forecast/latLong/?format={format}&latitude={latitude}&longitude={longitude}&date={date}&distance={distance}&API_KEY=D79713AA-E89D-47F5-9F30-AA857EB839A7"

        # Make the GET request
        response = requests.get(url)
        response.raise_for_status()  # Raise an exception for HTTP errors

        # Parse the JSON response
        data = response.json()
        #print(data)

        if data:
          response_text = {"Reporting Area": data[0]["ReportingArea"] + ", " + data[0]["StateCode"],
                          "ParameterName": data[0]["ParameterName"],
                          "Forecasts": []}  # Initialize an empty list for forecasts
          #print(response_text)
          for d in data:
            #print(d)
            forecast_data = {
                "DateForecast": d["DateForecast"],
                "AQI": d["AQI"],
                "ActionDay": bool(d["ActionDay"]),
                #"Discussion": d["Discussion"],
                "CategoryNumber": d["Category"]["Number"],
                "CategoryName": d["Category"]["Name"]
            }
            #print(forecast_data)
            response_text["Forecasts"].append(forecast_data)  # Append forecast data to the list
            #print(response_text)

          return response_text
        else:
          return {"error": "No data available"}
    except requests.RequestException as e:
        return {"error": f"Failed to fetch air quality data: {str(e)}"}
    except KeyError:
        return {"error": "Unexpected response format"}
    
# Setup the tools and include user defined functions
tools = [
    # {
    #     "type": "function",
    #     "function": {
    #         "name": "get_current_weather",
    #         "description": "Get the current weather using latitude and longitude",
    #         "parameters": {
    #             "type": "object",
    #             "properties": {
    #                 "latitude": {
    #                     "type": "number",
    #                     "description": "The latitude of the location, e.g., 37.7749",
    #                 },
    #                 "longitude": {
    #                     "type": "number",
    #                     "description": "The longitude of the location, e.g., -122.4194",
    #                 }
    #             },
    #             "required": ["latitude", "longitude"],
    #             "additionalProperties": False
    #         },
    #         "strict": True
    #     }
    # },
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
    openai.pydantic_function_tool(GetCurrentAirQuality),
]

available_functions = {
    "GetCurrentAirQuality": get_current_airquality,
    #"get_current_weather": get_current_weather,
    "send_email": send_email,

}
#***********************************
# Helper functions
#***********************************
def process_message_content(content):
    """Process message content to convert various image references to HTML."""
    # Pattern for explicit <image> tags
    pattern1 = r'<image>(.*?)</image>'
    
    # Pattern for Markdown-style image syntax (i.e. ![alt text](image path))
    pattern2 = r'!\[([^\]]+)\]\((images/[^)]+)\)'
    
    # Pattern for parenthetical image references (i.e. (images/some_image.jpg))
    pattern3 = r'\(images/([^)]+)\)'

    # Replace <image> tags with <img> tags
    content = re.sub(
        pattern1, 
        r'<img src="/images/\1" alt="Resource Image" class="chat-image" />', 
        content
    )

    # Replace Markdown-style image references with <img> tags
    content = re.sub(
        pattern2,
        r'<img src="/images/\2" alt="\1" class="chat-image" />',
        content
    )

    # Replace parenthetical image references with <img> tags
    content = re.sub(
        pattern3, 
        r'<img src="/images/\1" alt="Resource Image" class="chat-image" />', 
        content
    )

    return content


def process_text_message_content(response_message_content):
    # First, remove leading and trailing whitespace and replace newlines with a space to prevent extra line breaks
    formatted_response = response_message_content.strip().replace("\n", " ")

    # Convert Markdown-style links [text](url) to HTML links
    formatted_response = re.sub(
        r'\[([^\]]+)\]\(([^)]+)\)',
        r'<a href="\2" target="_blank" class="chat-link">\1</a>',
        formatted_response
    )
    
    # Convert plain URLs to clickable links (for URLs not in Markdown format)
    formatted_response = re.sub(
        r'(?<![\(\["])(https?://[^\s<>"]+|www\.[^\s<>"]+)(?![\)\]"])',
        r'<a href="\1" target="_blank" class="chat-link">\1</a>',
        formatted_response
    )

    # Replace headings with bold and add line breaks
    formatted_response = re.sub(r'###\s*(.*?):', r'<br><strong>\1:</strong>', formatted_response)
    
    # Format numbered lists without extra line breaks
    formatted_response = re.sub(
        r'(\d+\.\s*\*\*[^*]+\*\*)',
        r'<br>\1',
        formatted_response
    )

    # Format bullet points with proper spacing, avoiding extra <br>
    formatted_response = re.sub(
        r'-\s+\*\*([^*]+)\*\*:?',
        r'<br>&emsp;• <strong>\1</strong>:',
        formatted_response
    )

    # Regular bullet points (without extra line breaks)
    formatted_response = re.sub(
        r'-\s+([^<])',
        r'<br>&emsp;• \1',
        formatted_response
    )
    
    # Convert markdown bold to HTML <strong> tags
    formatted_response = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', formatted_response)

    # Now remove all consecutive <br> tags, leaving only one line break
    formatted_response = re.sub(r'<br>\s*<br>', r'<br>', formatted_response)

    # Finally, ensure no excessive spaces around <br> tags
    formatted_response = re.sub(r'\s*<br>\s*', r'<br>', formatted_response)

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
        Please respond with the number that corresponds to your role, or feel free to ask any question directly.
        """
        
        full_greeting = greeting + user_type_prompt
        
        # Add greeting to chat history and context
        chat_history.append((full_greeting, "bot", timestamp))
        chatContext.append({'role': 'assistant', 'content': full_greeting})
        
        return full_greeting
    except Exception as e:
        print(f"Error getting initial greeting: {e}")
        error_message = """
        Welcome to {CHATBOT_NAME}. We're here to help during this challenging time.
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
        Please respond with the number that corresponds to your role, or feel free to ask any question directly.
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
        # Step 1: Get today's date dynamically
        today_date = datetime.date.today().strftime("%Y-%m-%d")
        
        if tool_calls:
            # Step 3: call the function.
            chatContext.append(assistant_message)  # extend conversation with assistant's reply

            # Step 4: send the info for each function call and function response to the model
            for tool_call in tool_calls:
                function_name = tool_call.function.name
                print("GPT to call! function: ", function_name)
                function_to_call = available_functions[function_name]
                function_args = json.loads(tool_call.function.arguments)
                # Step 2: Add today's date to the function arguments (if not already present)
                function_args['date'] = today_date

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

        # Convert markdown bold to HTML
        formatted_response = process_text_message_content(response_message_content)
        
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
        if chat_history and "tell me your role" in chat_history[-1][0].lower() and user_input.strip() in ['1', '2', '3', '4']:
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