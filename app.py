import os
import time
from dotenv import load_dotenv
import openai
from flask import Flask, render_template, request, send_from_directory
import re

# Load environment variables
load_dotenv()

# Initialize OpenAI client with API key
openai.api_key = os.getenv('OPENAI_API_KEY')

# Flask app setup
app = Flask(__name__)

@app.route('/images/<path:filename>')
def images(filename):
    return send_from_directory('images', filename)

@app.route('/css/<path:filename>')
def css(filename):
    return send_from_directory('css', filename)

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

def chat_complete_messages(messages, temperature=0):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=temperature,
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error with OpenAI API: {e}")
        return "Sorry, there was an issue processing your request."

    return processed_content

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
        response_message_content = chat_complete_messages(chatContext, 0)
        
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
        
        # Add extra spacing between sections
        #formatted_response = formatted_response.replace("</strong><br>", "</strong><br><br>")
        
        # Process any image tags
        processed_response = process_message_content(formatted_response)
        
        # Add bot response to context and chat history
        chatContext.append({'role': 'assistant', 'content': response_message_content})
        chat_history.append((processed_response, "bot", timestamp))
        
        return processed_response
        
    except Exception as e:
        print(f"Error processing response: {e}")
        return f"I apologize, but I encountered an error while processing your request. Please try again."
    
    
def process_user_type_selection(user_input):
    """Process user type selection and generate appropriate response"""
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
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