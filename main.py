from datetime import datetime
from firebase import firebase
import requests
from recipe import Recipe

firebase_url = "https://souschef-182502.firebaseio.com"
souschef_url = "https://souschef-182502.appspot.com"

fb = firebase.FirebaseApplication(firebase_url)


# --------------- Helpers that build all of the responses ----------------------

def build_speechlet_response(title, output, reprompt_text, should_end_session):
    return {
        'outputSpeech': {
            'type': 'PlainText',
            'text': output
        },
        'card': {
            'type': 'Simple',
            'title': "SessionSpeechlet - " + title,
            'content': "SessionSpeechlet - " + output
        },
        'reprompt': {
            'outputSpeech': {
                'type': 'PlainText',
                'text': reprompt_text
            }
        },
        'shouldEndSession': should_end_session
    }


def build_response(session_attributes, speechlet_response):
    return {
        'version': '1.0',
        'sessionAttributes': session_attributes,
        'response': speechlet_response
    }


# --------------- Helpers  ----------------------

def get_current_meal():
    curr_time = datetime.now()
    if 4 < curr_time.hour < 12:
        return curr_time.weekday(), "Breakfast"
    elif 12 < curr_time.hour < 17:
        return curr_time.weekday(), "Lunch"
    else:
        return curr_time.weekday(), "Dinner"


def get_recipe_details(day, meal_type, user_id=1):
    recipe = fb.get('/users/{}/weekly_plan/{}/{}'.format(user_id, day, meal_type), None)
    return recipe


def get_recipe_instructions(recipe_id):
    url = "{}/api/v1/recipes/recipe_steps?recipe_id={}".format(souschef_url, recipe_id)
    r = requests.get(url)
    instructions = r.json()[0]['steps']
    return instructions


def get_recipe(user_id=1):
    day, meal_type = get_current_meal()
    recipe_details = get_recipe_details(day, meal_type, user_id)
    instructions = get_recipe_instructions(recipe_details["ID"])

    return recipe_details["ID"], recipe_details["Name"], instructions, meal_type


def get_next_step(steps, current_step):
    step = steps[current_step]

    out = "Step {}. {}".format(step["number"], step["step"])
    return out


def save_state(recipe_id, step, user_id=1):
    fb.put('alexa/', user_id, {'recipe_id': recipe_id, 'step': step})


def load_state(user_id=1):
    return fb.get('alexa/{}'.format(user_id), None)


def delete_state(user_id=1):
    return fb.put('alexa/', user_id, {})


# --------------- Functions that control the skill's behavior ------------------

def get_welcome_response():
    session_attributes = {}
    card_title = "Welcome to Sous Chef"
    speech_output = "Welcome to Sous Chef. Try saying Start Cooking"
    # If the user either does not reply to the welcome message or says something
    # that is not understood, they will be prompted again with this text.
    reprompt_text = "Try saying Start Cooking"
    should_end_session = False
    return build_response(session_attributes, build_speechlet_response(
        card_title, speech_output, reprompt_text, should_end_session))


def handle_session_end_request(session):
    if "current_recipe_id" in session.get("attributes", {}):
        current_recipe_id = session["attributes"]["current_recipe_id"]
        current_step = session["attributes"]["current_step"]
        save_state(current_recipe_id, current_step)


def handle_recipe_end():
    card_title = "Bon Appetit"
    speech_output = "Enjoy your food!"
    should_end_session = True
    return build_response({}, build_speechlet_response(
        card_title, speech_output, None, should_end_session))


def handle_start_cooking(session):
    should_end_session = False
    reprompt_text = None

    # alexa_uid = session["user"]["userId"]
    recipe_id, recipe_name, recipe_steps, meal_type = get_recipe()

    session_attributes = {"current_recipe_id": recipe_id,
                          "current_recipe_steps": recipe_steps,
                          "current_step": 0}

    speech_response = "Ok! For {} we're making {}. Say next to get the first step".format(meal_type, recipe_name)

    return build_response(session_attributes, build_speechlet_response("Success", speech_response,
                                                                       reprompt_text, should_end_session))


def handle_next_step(session):
    session_attributes = {}
    should_end_session = False
    reprompt_text = None
    # alexa_uid = session["user"]["userId"]

    if "current_recipe_id" in session.get("attributes", {}):
        current_recipe_steps = session["attributes"]["current_recipe_steps"]
        current_step = session["attributes"]["current_step"]
        session_attributes = session["attributes"]
    else:
        current_recipe = load_state()
        if current_recipe is None:
            speech_response = "Sorry, there is no ongoing recipe. Try saying Start Cooking."
            return build_response(session_attributes, build_speechlet_response("Failure", speech_response,
                                                                               reprompt_text, should_end_session))
        else:
            current_recipe_steps = get_recipe_instructions(current_recipe['recipe_id'])
            current_step = current_recipe['step']
            session_attributes = {"current_recipe_id": current_recipe['recipe_id'],
                                  "current_recipe_steps": current_recipe_steps,
                                  "current_step": current_step}

    if current_step >= len(current_recipe_steps):
        delete_state()

        return handle_recipe_end()

    speech_response = get_next_step(current_recipe_steps, current_step)
    session_attributes["current_step"] += 1
    return build_response(session_attributes, build_speechlet_response("Success", speech_response,
                                                                       reprompt_text, should_end_session))


# --------------- Events ------------------

def on_session_started(session_started_request, session):
    """ Called when the session starts """

    print("on_session_started requestId=" + session_started_request['requestId']
          + ", sessionId=" + session['sessionId'])


def on_launch(launch_request, session):
    """ Called when the user launches the skill without specifying what they
    want
    """

    print("on_launch requestId=" + launch_request['requestId'] +
          ", sessionId=" + session['sessionId'])
    # Dispatch to your skill's launch
    return get_welcome_response()


def on_intent(intent_request, session):
    """ Called when the user specifies an intent for this skill """

    print("on_intent requestId=" + intent_request['requestId'] +
          ", sessionId=" + session['sessionId'])

    intent = intent_request['intent']
    intent_name = intent['name']

    # Dispatch to your skill's intent handlers
    if intent_name == "StartCookingIntent":
        return handle_start_cooking(session)
    elif intent_name == "NextStepIntent":
        return handle_next_step(session)
    elif intent_name == "AMAZON.HelpIntent":
        return get_welcome_response()
    elif intent_name == "AMAZON.CancelIntent" or intent_name == "AMAZON.StopIntent":
        return handle_session_end_request(session)
    else:
        raise ValueError("Invalid intent")


def on_session_ended(session_ended_request, session):
    """ Called when the user ends the session.

    Is not called when the skill returns should_end_session=true
    """
    print("on_session_ended requestId=" + session_ended_request['requestId'] +
          ", sessionId=" + session['sessionId'])

    if "current_recipe_id" in session.get("attributes", {}):
        current_recipe_id = session["attributes"]["current_recipe_id"]
        current_step = session["attributes"]["current_step"]
        save_state(current_recipe_id, current_step)


# --------------- Main handler ------------------

def lambda_handler(event, context):
    """ Route the incoming request based on type (LaunchRequest, IntentRequest,
    etc.) The JSON body of the request is provided in the event parameter.
    """
    print("event.session.application.applicationId=" +
          event['session']['application']['applicationId'])

    """
    Uncomment this if statement and populate with your skill's application ID to
    prevent someone else from configuring a skill that sends requests to this
    function.
    """
    # if (event['session']['application']['applicationId'] !=
    #         "amzn1.echo-sdk-ams.app.[unique-value-here]"):
    #     raise ValueError("Invalid Application ID")

    if event['session']['new']:
        on_session_started({'requestId': event['request']['requestId']},
                           event['session'])

    if event['request']['type'] == "LaunchRequest":
        return on_launch(event['request'], event['session'])
    elif event['request']['type'] == "IntentRequest":
        return on_intent(event['request'], event['session'])
    elif event['request']['type'] == "SessionEndedRequest":
        return on_session_ended(event['request'], event['session'])
