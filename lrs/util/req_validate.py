import json
from lrs import models
from lrs.exceptions import Unauthorized, ParamConflict, ParamError
from django.contrib.auth import authenticate
import Authorization
import base64
import ast
from django.utils.decorators import decorator_from_middleware
import pdb
import pprint
import logging
from datetime import datetime
from django.utils.timezone import utc

REQUEST_TIME = datetime.utcnow().replace(tzinfo=utc).isoformat()

@Authorization.auth
def statements_post(r_dict):
    # pdb.set_trace()

    # TODO: MORE EFFICIENT WAY OF DOING THIS
    if r_dict['auth']:
        user_action = models.SystemAction(level='REQUEST', timestamp=REQUEST_TIME,
            message='POST /statements', content_object=r_dict['auth'])
    else:
        user_action = models.SystemAction(level='REQUEST', timestamp=REQUEST_TIME,
            message='POST /statements')

    user_action.save()
    r_dict['user_action'] = {'user': user_action.content_object, 'parent_id': user_action.id}

    if "application/json" not in r_dict['CONTENT_TYPE']:
        r_dict['method'] = 'GET'
    return r_dict

@Authorization.auth
def statements_get(r_dict):
    return r_dict

def check_for_existing_statementId(stmtID):
    exists = False
    stmt = models.statement.objects.filter(statement_id=stmtID)
    if stmt:
        exists = True
    return exists

def check_for_no_other_params_supplied(query_dict):
    supplied = True
    if len(query_dict) <= 1:
        supplied = False
    return supplied

@Authorization.auth
def statements_put(r_dict):
    try:
        if isinstance(r_dict['body'], str):
            try:
                r_dict['body'] = ast.literal_eval(r_dict['body'])
            except:
                r_dict['body'] = json.loads(r_dict['body'])        
        statement_id = r_dict['statementId']
    except KeyError:
        raise ParamError("Error -- statements - method = %s, but statementId paramater is missing" % r_dict['method'])
    
    if check_for_existing_statementId(statement_id):
        raise ParamConflict("StatementId conflict")

    if not check_for_no_other_params_supplied(r_dict['body']):
        raise ParamError("No Content supplied")
    return r_dict

@Authorization.auth
def activity_state_put(r_dict):
    try:
        r_dict['activityId']
    except KeyError:
        raise ParamError("Error -- activity_state - method = %s, but activityId parameter is missing.." % r_dict['method'])
    try:
        r_dict['agent']
    except KeyError:
        raise ParamError("Error -- activity_state - method = %s, but agent parameter is missing.." % r_dict['method'])
    try:
        r_dict['stateId']
    except KeyError:
        raise ParamError("Error -- activity_state - method = %s, but stateId parameter is missing.." % r_dict['method'])
    
    if 'body' not in r_dict:
        raise ParamError("Could not find the profile")
    r_dict['state'] = r_dict.pop('body')
    return r_dict

@Authorization.auth
def activity_state_get(r_dict):
    try:
        r_dict['activityId']
    except KeyError:
        raise ParamError("Error -- activity_state - method = %s, but activityId parameter is missing.." % r_dict['method'])
    try:
        r_dict['agent']
    except KeyError:
        raise ParamError("Error -- activity_state - method = %s, but agent parameter is missing.." % r_dict['method'])
    return r_dict

@Authorization.auth
def activity_state_delete(r_dict):
    try:
        r_dict['activityId']
    except KeyError:
        raise ParamError("Error -- activity_state - method = %s, but activityId parameter is missing.." % r_dict['method'])
    try:
        r_dict['agent']
    except KeyError:
        raise ParamError("Error -- activity_state - method = %s, but agent parameter is missing.." % r_dict['method'])
    return r_dict
  
@Authorization.auth
def activity_profile_put(r_dict):
    try:
        r_dict['activityId']
    except KeyError:
        raise ParamError("Error -- activity_profile - method = %s, but activityId parameter missing.." % r_dict['method'])
    
    try:
        r_dict['profileId']
    except KeyError:
        raise ParamError("Error -- activity_profile - method = %s, but profileId parameter missing.." % r_dict['method'])
    
    if 'body' not in r_dict:
        raise ParamError("Could not find the profile")

    bdy = r_dict.pop('body')
    r_dict['profile'] = bdy #json.dumps([i.values()[::-1] for i in bdy])
    
    return r_dict

@Authorization.auth
def activity_profile_get(r_dict):
    try:
        r_dict['activityId']
    except KeyError:
         raise ParamError("Error -- activity_profile - method = %s, but no activityId parameter.. the activityId parameter is required" % r_dict['method'])
    return r_dict

@Authorization.auth
def activity_profile_delete(r_dict):
    try:
        r_dict['activityId']
    except KeyError:
         raise ParamError("Error -- activity_profile - method = %s, but no activityId parameter.. the activityId parameter is required" % r_dict['method'])
    try:
        r_dict['profileId']
    except KeyError:
         raise ParamError("Error -- activity_profile - method = %s, but no profileId parameter.. the profileId parameter is required" % r_dict['method'])
    return r_dict


def activities_get(r_dict):
    try:
        r_dict['activityId']
    except KeyError:
        raise ParamError("Error -- activities - method = %s, but activityId parameter is missing" % r_dict['method'])
    return r_dict

@Authorization.auth
def agent_profile_put(r_dict):
    try: 
        r_dict['agent']
    except KeyError:
        raise ParamError("Error -- agent_profile - method = %s, but agent parameter missing.." % r_dict['method'])
    try:
        r_dict['profileId']
    except KeyError:
        raise ParamError("Error -- agent_profile - method = %s, but profileId parameter missing.." % r_dict['method'])
    
    if 'body' not in r_dict:
        raise ParamError("Could not find the profile")
    r_dict['profile'] = r_dict.pop('body')
    return r_dict


def agent_profile_get(r_dict):
    try: 
        r_dict['agent']
    except KeyError:
        raise ParamError("Error -- agent_profile - method = %s, but agent parameter missing.. the agent parameter is required" % r_dict['method'])
    return r_dict

@Authorization.auth
def agent_profile_delete(r_dict):
    try: 
        r_dict['agent']
    except KeyError:
        raise ParamError("Error -- agent_profile - method = %s, but no agent parameter.. the agent parameter is required" % r_dict['method'])
    try:
        r_dict['profileId']
    except KeyError:
        raise ParamError("Error -- agent_profile - method = %s, but no profileId parameter.. the profileId parameter is required" % r_dict['method'])
    return r_dict


def agents_get(r_dict):
    try: 
        r_dict['agent']
    except KeyError:
        raise ParamError("Error -- agents url, but no agent parameter.. the agent parameter is required")
    return r_dict


