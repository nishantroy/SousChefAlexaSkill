from datetime import datetime
import os
from firebase import firebase
import requests

firebase_url = "https://souschef-182502.firebaseio.com"
souschef_url = "https://souschef-182502.appspot.com"
firebase_secret = os.environ["FIREBASE_SECRET"]

fb = firebase.FirebaseApplication(firebase_url, firebase.FirebaseAuthentication(firebase_secret, ''))


# --------------- Helpers that build all of the responses ----------------------

def build_speechlet_response(title, output, reprompt_text, should_end_session):
    return {
        'outputSpeech': {
            'type': 'PlainText',
            'text': output
        },
        'card': {
            'type': 'Simple',
            'title': "SousChef - " + title,
            'content': output
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

def get_recipe_details(day, meal_type, user_id=1):
    recipe = fb.get('/users/{}/weekly_plan/{}/{}'.format(user_id, day, meal_type), None)
    return recipe


def get_recipe_instructions(recipe_id):
    url = "{}/api/v1/recipes/recipe_steps?recipe_id={}".format(souschef_url, recipe_id)
    r = requests.get(url)
    instructions = r.json()[0]['steps']
    return instructions


def get_ingredients(recipe_id):
    url = "{}/api/v1/recipes/recipe_details?recipe_id={}".format(souschef_url, recipe_id)
    print "URL: {}".format(url)
    r = requests.get(url)
    ingredients = r.json()['extendedIngredients']
    return ingredients


def get_recipe(meal_type, user_id=1):
    day = datetime.now().weekday()
    recipe_details = get_recipe_details(day, meal_type, user_id)
    instructions = get_recipe_instructions(recipe_details["ID"])

    return recipe_details["ID"], recipe_details["Name"], instructions


def get_next_step(steps, current_step):
    step = steps[current_step]

    out = "Step {}. {}".format(step["number"], step["step"])
    return out


def save_state(recipe_id, step, user_id=1):
    url = "{}/api/v1/users/save_current_recipe_progress?" \
          "user_id={}&recipe_id={}&step={}".format(souschef_url, user_id, recipe_id, step)
    requests.get(url)


def load_state(user_id=1):
    url = "{}/api/v1/users/get_current_recipe_progress?user_id={}".format(souschef_url, user_id)
    r = requests.get(url)
    return r.json()


def delete_state(user_id=1):
    url = "{}/api/v1/users/delete_current_recipe_progress?user_id={}".format(souschef_url, user_id)
    requests.get(url)


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
    session_attributes = {}
    speech_response = "Okay! I've saved your progress. Just say next or repeat when you want to resume."
    return build_response(session_attributes, build_speechlet_response("Stopped", speech_response, None, True))


def handle_recipe_end(session_attributes, user_id=1):
    delete_state(user_id)
    card_title = "Bon Appetit"
    speech_output = "You're all done! Enjoy your food!"
    should_end_session = True
    return build_response(session_attributes, build_speechlet_response(
        card_title, speech_output, None, should_end_session))


def handle_start_cooking(intent, session):
    should_end_session = False
    reprompt_text = None
    session_attributes = {}

    # alexa_uid = session["user"]["userId"]
    if "value" not in intent["slots"]["MealType"]:
        speech_response = "Do you want Breakfast, Lunch, or Dinner?"
        reprompt_text = speech_response
        return build_response(session_attributes,
                              build_speechlet_response("Which meal do you want to cook?", speech_response,
                                                       reprompt_text, should_end_session))

    meal_type = intent["slots"]["MealType"]["value"].capitalize()

    recipe_id, recipe_name, recipe_steps = get_recipe(meal_type)

    session_attributes = {"current_recipe_id": recipe_id,
                          "current_recipe_steps": recipe_steps,
                          "current_step": 0}

    save_state(recipe_id, 0)
    speech_response = "Ok! For {} we're making {}. Say next to get the first step".format(meal_type, recipe_name)

    return build_response(session_attributes, build_speechlet_response("Let's start!", speech_response,
                                                                       reprompt_text, should_end_session))


def handle_next_step(session):
    session_attributes = {}
    should_end_session = False
    reprompt_text = None
    # alexa_uid = session["user"]["userId"]

    if "current_recipe_steps" in session.get("attributes", {}):
        current_recipe_steps = session["attributes"]["current_recipe_steps"]
        current_step = session["attributes"]["current_step"]
        session_attributes = session["attributes"]
    else:
        current_recipe = load_state()
        if current_recipe is None:
            speech_response = "Sorry, there is no ongoing recipe. Try saying Start Cooking."
            return build_response(session_attributes, build_speechlet_response("Failure", speech_response,
                                                                               reprompt_text, should_end_session))
        current_recipe_steps = get_recipe_instructions(current_recipe['recipe_id'])
        current_step = current_recipe['step']
        session_attributes = {"current_recipe_id": current_recipe['recipe_id'],
                              "current_recipe_steps": current_recipe_steps,
                              "current_step": current_step}

    if current_step >= len(current_recipe_steps):
        return handle_recipe_end(session_attributes)

    speech_response = get_next_step(current_recipe_steps, current_step)
    session_attributes["current_step"] += 1
    return build_response(session_attributes, build_speechlet_response("Next Step", speech_response,
                                                                       reprompt_text, should_end_session))


def handle_repeat_step(session):
    session_attributes = {}
    should_end_session = False
    reprompt_text = None
    # alexa_uid = session["user"]["userId"]

    if "current_recipe_steps" in session.get("attributes", {}):
        current_recipe_steps = session["attributes"]["current_recipe_steps"]
        current_step = session["attributes"]["current_step"]
        session_attributes = session["attributes"]
    else:
        current_recipe = load_state()
        if current_recipe is None:
            speech_response = "Sorry, there is no ongoing recipe. Try saying Start Cooking."
            return build_response(session_attributes, build_speechlet_response("Failure", speech_response,
                                                                               reprompt_text, should_end_session))
        current_recipe_steps = get_recipe_instructions(current_recipe['recipe_id'])
        current_step = current_recipe['step']
        session_attributes = {"current_recipe_id": current_recipe['recipe_id'],
                              "current_recipe_steps": current_recipe_steps,
                              "current_step": current_step}

    current_step -= 1

    if current_step < 0:
        current_step = 0

    session_attributes["current_step"] = current_step + 1
    speech_response = get_next_step(current_recipe_steps, current_step)
    return build_response(session_attributes, build_speechlet_response("Repeat Step", speech_response,
                                                                       reprompt_text, should_end_session))


def handle_previous_step(session):
    session_attributes = {}
    should_end_session = False
    reprompt_text = None
    # alexa_uid = session["user"]["userId"]

    if "current_recipe_steps" in session.get("attributes", {}):
        current_recipe_steps = session["attributes"]["current_recipe_steps"]
        current_step = session["attributes"]["current_step"]
        session_attributes = session["attributes"]
    else:
        current_recipe = load_state()
        if current_recipe is None:
            speech_response = "Sorry, there is no ongoing recipe. Try saying Start Cooking."
            return build_response(session_attributes, build_speechlet_response("Failure", speech_response,
                                                                               reprompt_text, should_end_session))
        current_recipe_steps = get_recipe_instructions(current_recipe['recipe_id'])
        current_step = current_recipe['step']
        session_attributes = {"current_recipe_id": current_recipe['recipe_id'],
                              "current_recipe_steps": current_recipe_steps,
                              "current_step": current_step}

    current_step -= 2

    if current_step < 0:
        current_step = 0
    session_attributes["current_step"] = current_step + 1
    speech_response = get_next_step(current_recipe_steps, current_step)
    return build_response(session_attributes, build_speechlet_response("Previous Step", speech_response,
                                                                       reprompt_text, should_end_session))


def handle_ingredient_list(session):
    session_attributes = {}
    should_end_session = False
    reprompt_text = None

    if "current_recipe_id" in session.get("attributes", {}):
        current_recipe_id = session["attributes"]["current_recipe_id"]
        session_attributes = session["attributes"]
    else:
        current_recipe = load_state()
        if current_recipe is None:
            speech_response = "Sorry, there is no ongoing recipe. Try saying Start Cooking."
            return build_response(session_attributes, build_speechlet_response("Failure", speech_response,
                                                                               reprompt_text, should_end_session))
        current_recipe_id = current_recipe['recipe_id']

    current_recipe_ingredients = get_ingredients(current_recipe_id)
    speech_response = ", ".join([ingredient['originalString'] for ingredient in current_recipe_ingredients])
    return build_response(session_attributes, build_speechlet_response("Ingredients", speech_response,
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
        return handle_start_cooking(intent, session)
    elif intent_name == "NextStepIntent":
        return handle_next_step(session)
    elif intent_name == "RepeatStepIntent":
        return handle_repeat_step(session)
    elif intent_name == "PreviousStepIntent":
        return handle_previous_step(session)
    elif intent_name == "IngredientListIntent":
        return handle_ingredient_list(session)
    elif intent_name == "AMAZON.HelpIntent":
        return get_welcome_response()
    elif intent_name == "AMAZON.CancelIntent" or intent_name == "AMAZON.StopIntent":
        return handle_session_end_request(session)
    else:
        raise ValueError("Invalid intent")


def on_session_ended(session_ended_request, session):
    """ Called when the session times out.

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
