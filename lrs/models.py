from django.db import models
from django.db import transaction
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes import generic
from django.contrib.contenttypes.generic import GenericForeignKey
from django.core import serializers
from logging import INFO, WARN, WARNING, ERROR, CRITICAL, DEBUG, FATAL, NOTSET
from datetime import datetime
import datetime as dt
from django.utils.timezone import utc
from lrs.exceptions import IDNotFoundError, ParamError
import ast
import pytz
import json
import logging
import uuid
import pdb
import urllib
import urlparse
from time import time
from oauth_provider.managers import TokenManager, ConsumerManager, ResourceManager
from oauth_provider.consts import KEY_SIZE, SECRET_SIZE, CONSUMER_KEY_SIZE, CONSUMER_STATES,\
                   PENDING, VERIFIER_SIZE, MAX_URL_LENGTH

ADL_LRS_STRING_KEY = 'ADL_LRS_STRING_KEY'

gen_pwd = User.objects.make_random_password
generate_random = User.objects.make_random_password

def gen_uuid():
    return uuid.uuid4().hex

class Nonce(models.Model):
    token_key = models.CharField(max_length=KEY_SIZE)
    consumer_key = models.CharField(max_length=CONSUMER_KEY_SIZE)
    key = models.CharField(max_length=255)
    
    def __unicode__(self):
        return u"Nonce %s for %s" % (self.key, self.consumer_key)


class Resource(models.Model):
    name = models.CharField(max_length=255)
    url = models.TextField(max_length=MAX_URL_LENGTH)
    is_readonly = models.BooleanField(default=True)
    
    objects = ResourceManager()

    def __unicode__(self):
        return u"Resource %s with url %s" % (self.name, self.url)


class Consumer(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField()
    
    key = models.CharField(max_length=CONSUMER_KEY_SIZE, unique=True, default=gen_uuid)
    secret = models.CharField(max_length=SECRET_SIZE, default=gen_pwd)

    status = models.SmallIntegerField(choices=CONSUMER_STATES, default=PENDING)
    user = models.ForeignKey(User, null=True, blank=True, related_name="consumer_user")

    objects = ConsumerManager()
        
    def __unicode__(self):
        return u"Consumer %s with key %s" % (self.name, self.key)

    def generate_random_codes(self):
        """
        Used to generate random key/secret pairings.
        Use this after you've added the other data in place of save().
        """
        key = generate_random(length=KEY_SIZE)
        secret = generate_random(length=SECRET_SIZE)
        while Consumer.objects.filter(models.Q(key__exact=key) | models.Q(secret__exact=secret)).count():
            key = generate_random(length=KEY_SIZE)
            secret = generate_random(length=SECRET_SIZE)
        self.key = key
        self.secret = secret
        self.save()


class Token(models.Model):
    REQUEST = 1
    ACCESS = 2
    TOKEN_TYPES = ((REQUEST, u'Request'), (ACCESS, u'Access'))
    
    key = models.CharField(max_length=KEY_SIZE, null=True, blank=True)
    secret = models.CharField(max_length=SECRET_SIZE, null=True, blank=True)
    token_type = models.SmallIntegerField(choices=TOKEN_TYPES)
    timestamp = models.IntegerField(default=long(time()))
    is_approved = models.BooleanField(default=False)
    lrs_auth_id = models.CharField(max_length=200, null=True)

    user = models.ForeignKey(User, null=True, blank=True, related_name='tokens')
    consumer = models.ForeignKey(Consumer)
    resource = models.ForeignKey(Resource)
    
    ## OAuth 1.0a stuff
    verifier = models.CharField(max_length=VERIFIER_SIZE)
    callback = models.CharField(max_length=MAX_URL_LENGTH, null=True, blank=True)
    callback_confirmed = models.BooleanField(default=False)
    
    objects = TokenManager()
    
    def __unicode__(self):
        return u"%s Token %s for %s" % (self.get_token_type_display(), self.key, self.consumer)

    def to_string(self, only_key=False):
        token_dict = {
            'oauth_token': self.key, 
            'oauth_token_secret': self.secret,
            'oauth_callback_confirmed': self.callback_confirmed and 'true' or 'error'
        }
        if self.verifier:
            token_dict['oauth_verifier'] = self.verifier

        if only_key:
            del token_dict['oauth_token_secret']
            del token_dict['oauth_callback_confirmed']

        return urllib.urlencode(token_dict)

    def generate_random_codes(self):
        """
        Used to generate random key/secret pairings. 
        Use this after you've added the other data in place of save(). 
        """
        key = generate_random(length=KEY_SIZE)
        secret = generate_random(length=SECRET_SIZE)
        while Token.objects.filter(models.Q(key__exact=key) | models.Q(secret__exact=secret)).count():
            key = generate_random(length=KEY_SIZE)
            secret = generate_random(length=SECRET_SIZE)
        self.key = key
        self.secret = secret
        self.save()

    def get_callback_url(self):
        """
        OAuth 1.0a, append the oauth_verifier.
        """
        if self.callback and self.verifier:
            parts = urlparse.urlparse(self.callback)
            scheme, netloc, path, params, query, fragment = parts[:6]
            if query:
                query = '%s&oauth_verifier=%s' % (query, self.verifier)
            else:
                query = 'oauth_verifier=%s' % self.verifier
            return urlparse.urlunparse((scheme, netloc, path, params,
                query, fragment))
        return self.callback

import time
def filename(instance, filename):
    print filename
    return filename

class SystemAction(models.Model):
    REQUEST = 1 #should fall in debug level, only works cuz we manually enter this in db
    STMT_REF = 21 #using info level so that it's picked up by logger
    LEVEL_TYPES = (
        (REQUEST, 'REQUEST'),
        (STMT_REF, 'The statement'),
        (INFO, logging.getLevelName(INFO)), #20
        (WARN, logging.getLevelName(WARN)), #30
        (WARNING, logging.getLevelName(WARNING)), #30 
        (ERROR, logging.getLevelName(ERROR)), #40
        (CRITICAL, logging.getLevelName(CRITICAL)), #50
        (DEBUG, logging.getLevelName(DEBUG)), #10
        (FATAL, logging.getLevelName(FATAL)), #50
        (NOTSET, logging.getLevelName(NOTSET)), #0
    )
    level = models.SmallIntegerField(choices=LEVEL_TYPES)
    parent_action = models.ForeignKey('self', blank=True, null=True)
    message = models.TextField()
    timestamp = models.DateTimeField()
    status_code = models.CharField(max_length=50, blank=True, null=True)
    #Content_type is the user since it can be a User or group object
    content_type = models.ForeignKey(ContentType, null=True, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    content_object = generic.GenericForeignKey('content_type', 'object_id')

    def __unicode__(self):
        return "[%s(%s)] %s -- by: %s" % (self.get_level_display(),self.level, self.message, self.content_object)

    def days_til_del(self):
        deleteday = self.timestamp + dt.timedelta(days=settings.DAYS_TO_LOG_DELETE)
        days = (deleteday - datetime.utcnow().replace(tzinfo = pytz.utc)).days
        if days <= 0:
            days = 0
        return days

    def get_color(self):
        color = 'black'
        try:
            code = int(self.status_code)
            if code >= 200 and code < 300:
                color = 'green'
            elif code >=300 and code < 400:
                color = 'darkorange'
            else:
                color = 'darkred'
        except:
            pass
        return color

    def object_return(self):
        ret = {}
        ret['message_type'] = self.get_level_display()
        if not self.parent_action:
            ret['statuscode'] = self.status_code
        ret['message'] = self.message
        ret['timestamp'] = str(self.timestamp)
        return ret


class LanguageMap(models.Model):
    key = models.CharField(max_length=200, db_index=True)
    value = models.CharField(max_length=200)
    content_type = models.ForeignKey(ContentType)
    object_id = models.PositiveIntegerField()
    content_object = generic.GenericForeignKey('content_type', 'object_id')
    
    def object_return(self):
        return {self.key: self.value}

    def __unicode__(self):
        return json.dumps(self.object_return())


class Verb(models.Model):
    verb_id = models.CharField(max_length=200, db_index=True)
    display = generic.GenericRelation(LanguageMap)

    def object_return(self, lang=None):
        ret = {}
        ret['id'] = self.verb_id
        
        if lang is not None:
            lang_map_set = self.display.filter(key=lang)
        else:
            lang_map_set = self.display.all() 

        if len(lang_map_set) > 0:
            ret['display'] = {}
            for lang_map in lang_map_set:
                ret['display'].update(lang_map.object_return())        
        return ret

    # TODO: if this isn't good enough.. fix
    def get_display(self, lang=None):
        if not len(self.display.all()) > 0:
            return self.verb_id
        if lang:
            try:
                return self.display.get(key=lang).value
            except:
                pass
        try:
            return self.display(key='en-US').value
        except:
            try:
                return self.display(key='en').value
            except:
                pass
        return self.display.all()[0].value

    def __unicode__(self):
        return json.dumps(self.object_return())         


class extensions(models.Model):
    key=models.CharField(max_length=200, db_index=True)
    value=models.CharField(max_length=200)
    content_type = models.ForeignKey(ContentType)
    object_id = models.PositiveIntegerField()
    content_object = generic.GenericForeignKey('content_type', 'object_id')

    def object_return(self):
        return {self.key:self.value}

    def __unicode__(self):
        return json.dumps(self.object_return())


class result(models.Model): 
    success = models.NullBooleanField(blank=True,null=True)
    completion = models.NullBooleanField(blank=True,null=True)
    response = models.CharField(max_length=200, blank=True, null=True)
    #Made charfield since it would be stored in ISO8601 duration format
    duration = models.CharField(max_length=200, blank=True, null=True)
    extensions = generic.GenericRelation(extensions)
    content_type = models.ForeignKey(ContentType)
    object_id = models.PositiveIntegerField()
    content_object = generic.GenericForeignKey('content_type', 'object_id')

    def object_return(self):
        ret = {}
        
        if self.success:
            ret['success'] = self.success

        if self.completion:
            ret['completion'] = self.completion

        if self.response:
            ret['response'] = self.response

        if self.duration:
            ret['duration'] = self.duration
                        
        try:
            ret['score'] = self.score.object_return()
        except score.DoesNotExist:
            pass

        result_ext = self.extensions.all()
        if len(result_ext) > 0:
            ret['extensions'] = {}
            for ext in result_ext:
                ret['extensions'].update(ext.object_return())        
        return ret

    def __unicode__(self):
        return json.dumps(self.object_return())            


class score(models.Model):  
    scaled = models.FloatField(blank=True, null=True)
    raw = models.PositiveIntegerField(blank=True, null=True)
    score_min = models.PositiveIntegerField(blank=True, null=True)
    score_max = models.PositiveIntegerField(blank=True, null=True)
    result = models.OneToOneField(result, blank=True, null=True)
    
    def __init__(self, *args, **kwargs):
        the_min = kwargs.pop('min', None)
        the_max = kwargs.pop('max', None)
        super(score, self).__init__(*args, **kwargs)
        if the_min:
            self.score_min = the_min
        if the_max:
            self.score_max = the_max

    def object_return(self):
        ret = {}
        for field in self._meta.fields:
            if field.name != 'id' and field.name != 'result':
                value = getattr(self, field.name)
                if not value is None:
                    if field.name is 'score_min':
                        ret['min'] = value
                    elif field.name is 'score_max':
                        ret['max'] = value
                    else:
                        ret[field.name] = value
        return ret

    def __unicode__(self):
        return json.dumps(self.object_return())


class statement_object(models.Model):
    def get_a_name(self):
        return "please override"

agent_attrs_can_only_be_one = ('mbox', 'mbox_sha1sum', 'openid', 'account')
class agentmgr(models.Manager):
    def gen(self, **kwargs):
        group = kwargs.get('objectType', None) == "Group"
        attrs = [a for a in agent_attrs_can_only_be_one if kwargs.get(a, None) != None]
        if not group and len(attrs) != 1:
            raise ParamError('One and only one of %s may be supplied' % ', '.join(agent_attrs_can_only_be_one))
        val = kwargs.pop('account', None)
        if val:
            if not isinstance(val, dict):
                try:
                    account = ast.literal_eval(val)
                except:
                    account = json.loads(val)
            else:
                account = val
            try:
                acc = agent_account.objects.get(**account)
                ret_agent = acc.agent
                created = False
            except agent_account.DoesNotExist:
                if group:
                    try: 
                        ret_agent = self.model.objects.get(**kwargs)
                    except self.model.DoesNotExist:
                        ret_agent = self.model(**kwargs)
                else:
                    try:
                        ret_agent = agent.objects.get(**kwargs)
                    except agent.DoesNotExist:
                        ret_agent = agent(**kwargs)
                ret_agent.save()
                acc = agent_account(agent=ret_agent, **account)
                acc.save()
                created = True
        else:
            if group and 'member' in kwargs:
                mem = kwargs.pop('member')
                try:
                    members = ast.literal_eval(mem)
                except:
                    try:
                        members = json.loads(mem)
                    except:
                        members = mem
        try:
            # Added in if stmts to check if should get/create group or agent object
            # Before it was creating agents as groups
            if group:
                ret_agent = self.get(**kwargs)
            else:
                ret_agent = agent.objects.get(**kwargs)
            created = False
        except agent.DoesNotExist:
            if group:
                ret_agent = self.model(**kwargs)
            else:
                ret_agent = agent(**kwargs)
            ret_agent.save()
            created = True
        if group:
            ags = [self.gen(**a) for a in members]
            ret_agent.member.add(*(a for a, c in ags))
        ret_agent.save()
        return ret_agent, created

class agent(statement_object):
    objectType = models.CharField(max_length=200, blank=True, default="Agent")
    name = models.CharField(max_length=200, blank=True, null=True)
    mbox = models.CharField(max_length=200, blank=True, null=True, db_index=True)
    mbox_sha1sum = models.CharField(max_length=200, blank=True, null=True, db_index=True)
    openid = models.CharField(max_length=200, blank=True, null=True, db_index=True)
    objects = agentmgr()

    def get_agent_json(self, sparse=False):
        ret = {}
        # Default to agent, if group subclass calls it displays Group instead of Agent
        ret['objectType'] = self.objectType
        if self.name:
            ret['name'] = self.name
        if self.mbox:
            ret['mbox'] = self.mbox
        if self.mbox_sha1sum:
            ret['mbox_sha1sum'] = self.mbox_sha1sum
        if self.openid and not sparse:
            ret['openid'] = self.openid
        try:
            if not sparse:
                ret['account'] = self.agent_account.get_json()
        except:
            pass
        return ret

    def get_person_json(self):
        ret = {}
        ret['objectType'] = self.objectType
        if self.name:
            ret['name'] = [self.name]
        if self.mbox:
            ret['mbox'] = [self.mbox]
        if self.mbox_sha1sum:
            ret['mbox_sha1sum'] = [self.mbox_sha1sum]
        if self.openid:
            ret['openid'] = [self.openid]
        try:
            ret['account'] = [self.agent_account.get_json()]
        except:
            pass
        return ret

    def get_a_name(self):
        if self.name:
            return self.name
        if self.mbox:
            return self.mbox
        if self.mbox_sha1sum:
            return self.mbox_sha1sum
        if self.openid:
            return self.openid
        try:
            return self.agent_account.get_a_name()
        except:
            pass
        return "unknown"

    def __unicode__(self):
        return json.dumps(self.get_agent_json())


class agent_account(models.Model):  
    homePage = models.CharField(max_length=200, blank=True, null=True)
    name = models.CharField(max_length=200)
    agent = models.OneToOneField(agent)

    def get_json(self):
        ret = {}
        ret['homePage'] = self.homePage
        ret['name'] = self.name
        return ret
    
    def equals(self, other):
        if not isinstance(other, self.__class__):
            raise TypeError('Only models of same class can be compared')
        return self.name == other.name and self.homePage == other.homePage 

    def get_a_name(self):
        return self.name

    def __unicode__(self):
        return json.dumps(self.get_json())


class group(agent):
    member = models.ManyToManyField(agent, related_name="agents")
    objects = agentmgr()

    def __init__(self, *args, **kwargs):
        kwargs["objectType"] = "Group"
        super(group, self).__init__(*args, **kwargs)

    def get_agent_json(self, sparse=False):
        ret = {}
        ret['objectType'] = self.objectType
        ret['member'] = [a.get_agent_json(sparse) for a in self.member.all()]
        return ret

    def get_a_name(self):
        name = super(group, self).get_a_name()
        if not name:
            name = "anonymous group"
        return name


class agent_profile(models.Model):
    profileId = models.CharField(max_length=200, db_index=True)
    updated = models.DateTimeField(auto_now_add=True, blank=True)
    agent = models.ForeignKey(agent)
    profile = models.FileField(upload_to="agent_profile")
    content_type = models.CharField(max_length=200,blank=True,null=True)
    etag = models.CharField(max_length=200,blank=True,null=True)
    user = models.ForeignKey(User, null=True, blank=True)

    def delete(self, *args, **kwargs):
        self.profile.delete()
        super(agent_profile, self).delete(*args, **kwargs)


class activity(statement_object):
    activity_id = models.CharField(max_length=200, db_index=True)
    objectType = models.CharField(max_length=200,blank=True, null=True, default="Activity") 
    authoritative = models.CharField(max_length=200, blank=True, null=True)

    def object_return(self, sparse=False, lang=None):
        ret = {}
        ret['id'] = self.activity_id
        ret['objectType'] = self.objectType
        try:
            ret['definition'] = self.activity_definition.object_return(lang)
        except activity_definition.DoesNotExist:
            pass

        if sparse:
            if 'definition' in ret:
                if 'correctresponsespattern' in ret['definition']:
                    del ret['definition']['correctresponsespattern']
                    ret['definition']['definition'] = ret['definition']['description'].keys()
                    ret['definition']['name'] = ret['definition']['name'].keys()
        return ret

    def get_a_name(self):
        try:
            return self.activity_definition.name.get(key='en-US').value
        except:
            return self.activity_id

    def __unicode__(self):
        return json.dumps(self.object_return())


class name_lang(models.Model):
    key = models.CharField(max_length=200, db_index=True)
    value = models.CharField(max_length=200)
    content_type = models.ForeignKey(ContentType)
    object_id = models.PositiveIntegerField()
    content_object = generic.GenericForeignKey('content_type', 'object_id')
    
    def object_return(self):
        return {self.key: self.value}

    def __unicode__(self):
        return json.dumps(self.object_return())

class desc_lang(models.Model):
    key = models.CharField(max_length=200, db_index=True)
    value = models.CharField(max_length=200)
    content_type = models.ForeignKey(ContentType)
    object_id = models.PositiveIntegerField()
    content_object = generic.GenericForeignKey('content_type', 'object_id')
    
    def object_return(self):
        return {self.key: self.value}

    def __unicode__(self):
        return json.dumps(self.object_return())


class activity_definition(models.Model):
    name = generic.GenericRelation(name_lang, related_name="name_lang")
    description = generic.GenericRelation(desc_lang, related_name="desc_lang")
    activity_definition_type = models.CharField(max_length=200, blank=True, null=True)
    interactionType = models.CharField(max_length=200, blank=True, null=True)
    activity = models.OneToOneField(activity)
    extensions = generic.GenericRelation(extensions)

    def object_return(self, lang=None):
        ret = {}
        if lang is not None:
            name_lang_map_set = self.name.filter(key=lang)
            desc_lang_map_set = self.description.filter(key=lang)
        else:
            name_lang_map_set = self.name.all()
            desc_lang_map_set = self.description.all()

        ret['name'] = {}
        ret['description'] = {}
        for lang_map in name_lang_map_set:
            ret['name'].update(lang_map.object_return())                   
        for lang_map in desc_lang_map_set:
            ret['description'].update(lang_map.object_return())

        ret['type'] = self.activity_definition_type
        
        if not self.interactionType is None:
            ret['interactionType'] = self.interactionType

        try:
            self.correctresponsespattern = self.activity_def_correctresponsespattern
        except activity_def_correctresponsespattern.DoesNotExist:
            self.correctresponsespattern = None

        if not self.correctresponsespattern is None:
            ret['correctResponsesPattern'] = []
            # Get answers
            answers = correctresponsespattern_answer.objects.filter(correctresponsespattern=self.correctresponsespattern)
            for a in answers:
                ret['correctResponsesPattern'].append(a.objReturn())            
            scales = activity_definition_scale.objects.filter(activity_definition=self)
            if scales:
                ret['scale'] = []
                for s in scales:
                    ret['scale'].append(s.object_return(lang))
            # Get choices
            choices = activity_definition_choice.objects.filter(activity_definition=self)
            if choices:
                ret['choices'] = []
                for c in choices:
                    ret['choices'].append(c.object_return(lang))
            # Get steps
            steps = activity_definition_step.objects.filter(activity_definition=self)
            if steps:
                ret['steps'] = []
                for st in steps:
                    ret['steps'].append(st.object_return(lang))
            # Get sources
            sources = activity_definition_source.objects.filter(activity_definition=self)
            if sources:
                ret['source'] = []
                for so in sources:
                    ret['source'].append(so.object_return(lang))
            # Get targets
            targets = activity_definition_target.objects.filter(activity_definition=self)
            if targets:
                ret['target'] = []
                for t in targets:
                    ret['target'].append(t.object_return(lang))            
        result_ext = self.extensions.all()
        if len(result_ext) > 0:
            ret['extensions'] = {}
            for ext in result_ext:
                ret['extensions'].update(ext.object_return())        
        return ret

    def __unicode__(self):
        return json.dumps(self.object_return())


class activity_def_correctresponsespattern(models.Model):
    activity_definition = models.OneToOneField(activity_definition, blank=True, null=True)

class correctresponsespattern_answer(models.Model):
    answer = models.TextField()
    correctresponsespattern = models.ForeignKey(activity_def_correctresponsespattern)    

    def objReturn(self):
        return self.answer

    def __unicode__(self):
        return objReturn()

class activity_definition_choice(models.Model):
    choice_id = models.CharField(max_length=200)
    description = generic.GenericRelation(LanguageMap)
    activity_definition = models.ForeignKey(activity_definition)

    def object_return(self, lang=None):
        ret = {}
        ret['id'] = self.choice_id
        ret['description'] = {}
        
        if lang is not None:
            lang_map_set = self.description.filter(key=lang)
        else:
            lang_map_set = self.description.all()

        for lang_map in lang_map_set:
            ret['description'].update(lang_map.object_return())
        
        return ret

class activity_definition_scale(models.Model):
    scale_id = models.CharField(max_length=200)
    description = generic.GenericRelation(LanguageMap)
    activity_definition = models.ForeignKey(activity_definition)

    def object_return(self, lang=None):
        ret = {}
        ret['id'] = self.scale_id
        ret['description'] = {}
        
        if lang is not None:
            lang_map_set = self.description.filter(key=lang)
        else:
            lang_map_set = self.description.all()

        for lang_map in lang_map_set:
            ret['description'].update(lang_map.object_return())
        return ret

class activity_definition_source(models.Model):
    source_id = models.CharField(max_length=200)
    description = generic.GenericRelation(LanguageMap)
    activity_definition = models.ForeignKey(activity_definition)
    
    def object_return(self, lang=None):
        ret = {}
        ret['id'] = self.source_id
        ret['description'] = {}
        if lang is not None:
            lang_map_set = self.description.filter(key=lang)
        else:
            lang_map_set = self.description.all()        

        for lang_map in lang_map_set:
            ret['description'].update(lang_map.object_return())
        return ret

class activity_definition_target(models.Model):
    target_id = models.CharField(max_length=200)
    description = generic.GenericRelation(LanguageMap)
    activity_definition = models.ForeignKey(activity_definition)
    
    def object_return(self, lang=None):
        ret = {}
        ret['id'] = self.target_id
        ret['description'] = {}
        if lang is not None:
            lang_map_set = self.description.filter(key=lang)
        else:
            lang_map_set = self.description.all()        

        for lang_map in lang_map_set:
            ret['description'].update(lang_map.object_return())
        return ret

class activity_definition_step(models.Model):
    step_id = models.CharField(max_length=200)
    description = generic.GenericRelation(LanguageMap)
    activity_definition = models.ForeignKey(activity_definition)

    def object_return(self, lang=None):
        ret = {}
        ret['id'] = self.step_id
        ret['description'] = {}
        if lang is not None:
            lang_map_set = self.description.filter(key=lang)
        else:
            lang_map_set = self.description.all()        

        for lang_map in lang_map_set:
            ret['description'].update(lang_map.object_return())
        return ret


class StatementRef(statement_object):
    object_type = models.CharField(max_length=12, default="StatementRef")
    ref_id = models.CharField(max_length=200)
    context = models.OneToOneField('context', blank=True, null=True)

    def object_return(self):
        ret = {}
        ret['objectType'] = "StatementRef"
        ret['id'] = self.ref_id
        return ret


class ContextActivity(models.Model):
    key = models.CharField(max_length=20, null=True)
    context_activity = models.CharField(max_length=200, null=True)
    context = models.ForeignKey('context')
    
    def object_return(self):
        ret = {}
        ret[self.key] = {}
        ret[self.key]['id'] = self.context_activity
        return ret


class context(models.Model):    
    registration = models.CharField(max_length=200)
    instructor = models.ForeignKey(agent,blank=True, null=True, on_delete=models.SET_NULL)
    team = models.ForeignKey(group,blank=True, null=True, on_delete=models.SET_NULL, related_name="context_team")
    revision = models.CharField(max_length=200,blank=True, null=True)
    platform = models.CharField(max_length=200,blank=True, null=True)
    language = models.CharField(max_length=200,blank=True, null=True)
    extensions = generic.GenericRelation(extensions)
    # for statement and sub statement
    content_type = models.ForeignKey(ContentType)
    object_id = models.PositiveIntegerField()
    content_object = generic.GenericForeignKey('content_type', 'object_id')

    def object_return(self, sparse=False):
        ret = {}
        linked_fields = ['instructor', 'team', 'cntx_statement', 'contextActivities']
        ignore = ['id', 'content_type', 'object_id', 'content_object']
        for field in self._meta.fields:
            if not field.name in ignore:
                value = getattr(self, field.name)
                if not value is None:
                    if not field.name in linked_fields:
                        ret[field.name] = value
                    elif field.name == 'instructor':
                        ret[field.name] = self.instructor.get_agent_json(sparse)
                    elif field.name == 'team':
                        ret[field.name] = self.team.get_agent_json()
                    elif field.name == 'cntx_statement':
                        ret['statement'] = self.cntx_statement.object_return()                    
        if self.contextactivity_set:
            ret['contextActivities'] = {}
            for con_act in self.contextactivity_set.all():
                ret['contextActivities'].update(con_act.object_return())
        try:
            ret['statement'] = self.statementref.object_return()
        except:
            pass  

        context_ext = self.extensions.all()
        if len(context_ext) > 0:
            ret['extensions'] = {}
            for ext in context_ext:
                ret['extensions'].update(ext.object_return())        
        return ret


class activity_state(models.Model):
    state_id = models.CharField(max_length=200)
    updated = models.DateTimeField(auto_now_add=True, blank=True)
    state = models.FileField(upload_to="activity_state")
    agent = models.ForeignKey(agent)
    activity = models.ForeignKey(activity)
    registration_id = models.CharField(max_length=200)
    content_type = models.CharField(max_length=200,blank=True,null=True)
    etag = models.CharField(max_length=200,blank=True,null=True)
    user = models.ForeignKey(User, null=True, blank=True)

    def delete(self, *args, **kwargs):
        self.state.delete()
        super(activity_state, self).delete(*args, **kwargs)

class activity_profile(models.Model):
    profileId = models.CharField(max_length=200)
    updated = models.DateTimeField(auto_now_add=True, blank=True)
    activity = models.ForeignKey(activity)
    profile = models.FileField(upload_to="activity_profile")
    content_type = models.CharField(max_length=200,blank=True,null=True)
    etag = models.CharField(max_length=200,blank=True,null=True)
    user = models.ForeignKey(User, null=True, blank=True)

    def delete(self, *args, **kwargs):
        self.profile.delete()
        super(activity_profile, self).delete(*args, **kwargs)


class SubStatement(statement_object):
    stmt_object = models.ForeignKey(statement_object, related_name="object_of_substatement")
    actor = models.ForeignKey(agent,related_name="actor_of_substatement")
    verb = models.ForeignKey(Verb)
    result = generic.GenericRelation(result)
    timestamp = models.DateTimeField(blank=True,null=True, default=lambda: datetime.utcnow().replace(tzinfo=utc).isoformat())
    context = generic.GenericRelation(context)
    user = models.ForeignKey(User, null=True, blank=True)

    def get_a_name(self):
        return self.stmt_object.statement_id
    
    def object_return(self, sparse=False, lang=None):
        activity_object = True
        ret = {}
        ret['actor'] = self.actor.get_agent_json(sparse)
        ret['verb'] = self.verb.object_return()

        try:
            stmt_object = activity.objects.get(id=self.stmt_object.id)
        except activity.DoesNotExist:
            try:
                stmt_object = agent.objects.get(id=self.stmt_object.id)
                activity_object = False
            except agent.DoesNotExist:
                raise IDNotFoundError('No activity or agent object found with given ID')
        if activity_object:
            ret['object'] = stmt_object.object_return(sparse, lang)  
        else:
            ret['object'] = stmt_object.get_agent_json(sparse)

        if len(self.result.all()) > 0:
            # if any, should only be 1
            ret['result'] = self.result.all()[0].object_return()
        if len(self.context.all()) > 0:
            ret['context'] = self.context.all()[0].object_return(sparse)
        ret['timestamp'] = str(self.timestamp)
        ret['objectType'] = "SubStatement"
        return ret

    def get_object(self):
        stmt_object = None
        object_type = None
        try:
            stmt_object = activity.objects.get(id=self.stmt_object.id)
            object_type = 'activity'
        except activity.DoesNotExist:
            try:
                stmt_object = agent.objects.get(id=self.stmt_object.id)
                object_type = 'agent'
            except agent.DoesNotExist:
                raise IDNotFoundError("No activity, or agent found with given ID")
        return stmt_object, object_type

    def delete(self, *args, **kwargs):
        # actor, verb, auth all detect this statement-stmt_object does not
        # Unvoid stmt if verb is voided
        stmt_object = None
        object_type = None

        stmt_object, object_type = self.get_object()

        if len(self.context.all()) > 0:
            self.context.all().delete()

        agent_links = [rel.get_accessor_name() for rel in agent._meta.get_all_related_objects()]
        # Get all possible relationships for actor
        actor_agent = agent.objects.get(id=self.actor.id)
        actor_in_use = False
        # Loop through each relationship
        for link in agent_links:
            if link != 'group':
                # Get all objects for that relationship that the agent is related to
                try:
                    objects = getattr(actor_agent, link).all()
                except:
                    continue
                # If looking at statement actors, if there's another stmt with same actor-in use
                if link == "actor_statement" or link == "actor_of_substatement":
                    # Will already have one (self)
                    if len(objects) > 1:
                        actor_in_use = True
                        break
                elif link == "object_of_statement":
                    # If for some reason actor is same as stmt_object, there will be at least one
                    if actor_agent == stmt_object :
                        if len(objects) > 1:
                            actor_in_use = True
                            break
                    # If they are not the same and theres at least one object, it's in use
                    else:
                        if len(objects) > 0:
                            actor_in_use = True
                            break
                # Agent doesn't appear in stmt anymore, if there are any other objects in any other relationships,
                # it's in use
                else:
                    if len(objects) > 0:
                        actor_in_use = True
                        break
        if not actor_in_use:
            self.actor.delete()
        
        verb_links = [rel.get_accessor_name() for rel in Verb._meta.get_all_related_objects()]
        verb_in_use = False
        # Loop through each relationship
        for link in verb_links:
            # Get all objects for that relationship that the agent is related to
            try:
                objects = getattr(self.verb, link).all()
            except:
                continue

            if link == "statement_set":
                if object_type == "substatement":
                    # There's at least one object (self)
                    if stmt_object.verb.verb_id == self.verb.verb_id:
                        if len(objects) > 1:
                            verb_in_use = True
                            break
                # Else there's a stmt using it 
                else:
                    if len(objects) > 0:
                        verb_in_use = True
                        break
            # Only other link is verb of stmt, there will be at least one for (self)
            else:
                if len(objects) > 1:
                    verb_in_use = True
                    break           

        # If nothing else is using it, delete it
        if not verb_in_use:
            self.verb.delete()

        object_in_use = False
        if object_type == 'activity':
            activity_links = [rel.get_accessor_name() for rel in activity._meta.get_all_related_objects()]
            for link in activity_links:
                try:
                    objects = getattr(stmt_object, link).all()
                except:
                    continue
                # There will be at least one (self)
                if link == 'object_of_statement':
                    if len(objects) > 1:
                        object_in_use = True
                        break
                # If it's anywhere else it's in use
                else:
                    if len(objects) > 0:
                        object_in_use = True
                        break
        elif object_type == 'agent':
            # Know it's not same as auth or actor
            for link in agent_links:
                if link != 'group':
                    try:
                        objects = getattr(stmt_object, link).all()
                    except:
                        continue
                    # There will be at least one (self)- DOES NOT PICK ITSELF UP BUT WILL PICK OTHERS UP
                    if link == 'object_of_statement':
                        if len(objects) > 0:
                            object_in_use = True 
                            break
                    # If it's in anything else outside of stmt then it's in use
                    else:
                        if len(objects) > 0:
                            object_in_use = True
                            break


        # If nothing else is using it, delete it
        if not object_in_use:
            stmt_object.delete()


class statement(models.Model):
    statement_id = models.CharField(max_length=200)
    stmt_object = models.ForeignKey(statement_object, related_name="object_of_statement")
    actor = models.ForeignKey(agent,related_name="actor_statement")
    verb = models.ForeignKey(Verb)
    result = generic.GenericRelation(result)
    stored = models.DateTimeField(auto_now_add=True,blank=True)
    timestamp = models.DateTimeField(blank=True,null=True, default=lambda: datetime.utcnow().replace(tzinfo=utc).isoformat())    
    authority = models.ForeignKey(agent, blank=True,null=True,related_name="authority_statement")
    voided = models.NullBooleanField(blank=True, null=True)
    context = generic.GenericRelation(context)
    authoritative = models.BooleanField(default=True)
    user = models.ForeignKey(User, null=True, blank=True)

    def get_a_name(self):
        return self.statement_id

    def get_stmt_object(self):
        object_type = 'activity'
        try:
            stmt_object = activity.objects.get(id=self.stmt_object.id)
        except activity.DoesNotExist:
            try:
                stmt_object = agent.objects.get(id=self.stmt_object.id)
                object_type = 'agent'
            except agent.DoesNotExist:
                try:
                    stmt_object = SubStatement.objects.get(id=self.stmt_object.id)
                    object_type = 'substatement'            
                except SubStatement.DoesNotExist:
                    try:
                        stmt_object = StatementRef.objects.get(id=self.stmt_object.id)
                        object_type = 'statementref'
                    except Exception, e:
                        raise IDNotFoundError("No activity, agent, substatement, or statementref found with given ID")
        return (stmt_object, object_type)

    def object_return(self, sparse=False, lang=None):
        object_type = 'activity'
        ret = {}
        ret['id'] = self.statement_id
        ret['actor'] = self.actor.get_agent_json(sparse)
        ret['verb'] = self.verb.object_return(lang)

        stmt_object, object_type = self.get_stmt_object()
        if object_type == 'activity' or object_type == 'substatement':
            ret['object'] = stmt_object.object_return(sparse, lang)  
        elif object_type == 'statementref':
            ret['object'] = stmt_object.object_return()
        else:
            ret['object'] = stmt_object.get_agent_json(sparse)
        if len(self.result.all()) > 0:
            # should only ever be one.. used generic fk to handle sub stmt and stmt
            ret['result'] = self.result.all()[0].object_return()        
        if len(self.context.all()) > 0:
            ret['context'] = self.context.all()[0].object_return(sparse)
        
        ret['timestamp'] = str(self.timestamp)
        ret['stored'] = str(self.stored)
        
        if not self.authority is None:
            ret['authority'] = self.authority.get_agent_json(sparse)
        
        ret['voided'] = self.voided
        return ret

    def save(self, *args, **kwargs):
        stmts = statement.objects.filter(actor=self.actor, stmt_object=self.stmt_object, authority=self.authority)
        cs = self.context.all()
        # narrow down list of statements to just those that have the same number of
        # context relations.. should be 0 or 1
        sl = [x for x in stmts if len(x.context.all()) == len(cs)]
        if len(cs) > 0:
            # if self has context, check to see if the statement has the same context
            sl = [s for s in sl if s.context.all()[0].id == cs.context.all().id]
        
        for s in sl:
            statement.objects.filter(id=s.id).update(authoritative=False)
        super(statement, self).save(*args, **kwargs)

    def get_object(self):
        stmt_object = None
        object_type = None
        try:
            stmt_object = activity.objects.get(id=self.stmt_object.id)
            object_type = 'activity'
        except activity.DoesNotExist:
            try:
                stmt_object = agent.objects.get(id=self.stmt_object.id)
                object_type = 'agent'
            except agent.DoesNotExist:
                try:
                    stmt_object = SubStatement.objects.get(id=self.stmt_object.id)
                    object_type = 'substatement'
                except SubStatement.DoesNotExist:
                    try:
                        stmt_object = StatementRef.objects.get(id=self.stmt_object.id)
                        object_type = 'statementref'
                    except Exception, e:
                        raise IDNotFoundError("No activity, agent, substatement, or statementref found with given ID")
        return stmt_object, object_type

    def unvoid_statement(self):
        statement_ref = StatementRef.objects.get(id=self.stmt_object.id)
        voided_stmt = statement.objects.filter(statement_id=statement_ref.ref_id).update(voided=False)

    def check_usage(self, links, obj, num):
        in_use = False
        # Loop through each relationship
        for link in links:
            if link != 'group':
                # Get all objects for that relationship that the agent is related to
                objects = getattr(obj, link).all()
                # If objects are more than one, other objects are using it
                if len(objects) > num:
                    in_use = True
                    break
        return in_use

    def delete(self, *args, **kwargs):
        # actor, verb, auth all detect this statement-stmt_object does not
        stmt_object = None
        object_type = None
        # Unvoid stmt if verb is voided
        if self.verb.verb_id == 'http://adlnet.gov/expapi/verbs/voided':
            self.unvoid_statement()
        # Else retrieve its object
        else:
            stmt_object, object_type = self.get_object()
        
        agent_links = [rel.get_accessor_name() for rel in agent._meta.get_all_related_objects()]
        # Get all possible relationships for actor
        actor_agent = agent.objects.get(id=self.actor.id)
        actor_in_use = False
        # Loop through each relationship
        for link in agent_links:
            if link != 'group':
                # Get all objects for that relationship that the agent is related to
                try:
                    objects = getattr(actor_agent, link).all()
                except:
                    continue
                # If looking at statement actors, if there's another stmt with same actor-in use
                if link == "actor_statement":
                    # Will already have one (self)
                    if len(objects) > 1:
                        actor_in_use = True
                        break
                # break check to see if this agent is the same as the auth
                elif link == "authority_statement":
                    # If auth
                    if not self.authority is None:
                        # If actor and auth are the same, there will be at least 1 object
                        if actor_agent == self.authority:
                            if len(objects) > 1:
                                actor_in_use = True
                                break
                        # If they are not the same and theres at least one object, it's a different obj using it
                        else:
                            if len(objects) > 0:
                                actor_in_use = True
                                break
                elif link == "object_of_statement":
                    # If for some reason actor is same as stmt_object, there will be at least one
                    if actor_agent == stmt_object :
                        if len(objects) > 1:
                            actor_in_use = True
                            break
                    # If they are not the same and theres at least one object, it's in use
                    else:
                        if len(objects) > 0:
                            actor_in_use = True
                            break
                # Agent doesn't appear in stmt anymore, if there are any other objects in any other relationships,
                # it's in use
                else:
                    if len(objects) > 0:
                        actor_in_use = True
                        break

        if not actor_in_use:
            self.actor.delete()
        
        if self.verb.verb_id != 'http://adlnet.gov/expapi/verbs/voided':
            verb_links = [rel.get_accessor_name() for rel in Verb._meta.get_all_related_objects()]
            verb_in_use = False
            # Loop through each relationship
            for link in verb_links:
                # Get all objects for that relationship that the agent is related to
                try:
                    objects = getattr(self.verb, link).all()
                except:
                    continue

                if link == "substatement_set":
                    if object_type == "substatement":
                        # If for some reason sub verb is same as verb, there will be at least one obj
                        if stmt_object.verb.verb_id == self.verb.verb_id:
                            if len(objects) > 1:
                                verb_in_use = True
                                break
                    # Else there's another sub using it 
                    else:
                        if len(objects) > 0:
                            verb_in_use = True
                            break
                # Only other link is verb of stmt, there will be at least one for (self)
                else:
                    if len(objects) > 1:
                        verb_in_use = True
                        break           

            # If nothing else is using it, delete it
            if not verb_in_use:
                self.verb.delete()

        if self.authority:
            authority_agent = agent.objects.get(id=self.authority.id)
            auth_in_use = False
            # If agents are the same and you already deleted the actor since it was in use, no use checking this
            if authority_agent != actor_agent:
                for link in agent_links:
                    if link != 'group':
                        try:
                            objects = getattr(authority_agent, link).all()
                        except:
                            continue

                        if link == "authority_statement":
                            # Will already have one (self)
                            if len(objects) > 1:
                                auth_in_use = True
                                break
                        elif link == "object_of_statement":
                            # If for some reason auth is same as stmt_object, there will be at least one
                            if authority_agent == stmt_object :
                                if len(objects) > 1:
                                    auth_in_use = True
                                    break
                            # If they are not the same and theres at least one object, it's in use
                            else:
                                if len(objects) > 0:
                                    auth_in_use = True
                                    break
                        # Don't have to check actor b/c you know it's different, and if it's in anything else outside
                        # of stmt then it's in use
                        else:
                            if len(objects) > 0:
                                auth_in_use = True
                                break                        
                if not auth_in_use:
                    self.authority.delete()
        
        if self.verb.verb_id != 'http://adlnet.gov/expapi/verbs/voided':
            object_in_use = False
            if object_type == 'activity':
                activity_links = [rel.get_accessor_name() for rel in activity._meta.get_all_related_objects()]
                for link in activity_links:
                    try:
                        objects = getattr(stmt_object, link).all()
                    except:
                        continue
                    # There will be at least one (self)
                    if link == 'object_of_statement':
                        if len(objects) > 1:
                            object_in_use = True
                            break
                    # If it's anywhere else it's in use
                    else:
                        if len(objects) > 0:
                            object_in_use = True
                            break
            elif object_type == 'substatement':
                sub_links = [rel.get_accessor_name() for rel in SubStatement._meta.get_all_related_objects()]
                # object_in_use = self.check_usage(sub_links, stmt_object, 1)
                for link in sub_links:
                    try:
                        objects = getattr(stmt_object, link).all()
                    except:
                        continue
                    # There will be at least one (self)
                    if link == 'object_of_statement':
                        if len(objects) > 1:
                            object_in_use = True
                            break
                    # If it's anything else then it's in use
                    else:
                        if len(objects) > 0:
                            object_in_use = True
                            break
            elif object_type == 'agent':
                # Know it's not same as auth or actor
                for link in agent_links:
                    if link != 'group':
                        try:
                            objects = getattr(stmt_object, link).all()
                        except:
                            continue
                        # There will be at least one (self)- DOES NOT PICK ITSELF UP BUT WILL PICK OTHERS UP
                        if link == 'object_of_statement':
                            if len(objects) > 0:
                                object_in_use = True 
                                break
                        # If it's in anything else outside of stmt then it's in use
                        else:
                            if len(objects) > 0:
                                object_in_use = True
                                break

            # If nothing else is using it, delete it
            if not object_in_use:
                stmt_object.delete()




# - from http://djangosnippets.org/snippets/2283/
# @transaction.commit_on_success
def merge_model_objects(primary_object, alias_objects=[], save=True, keep_old=False):
    """
    Use this function to merge model objects (i.e. Users, Organizations, Polls,
    etc.) and migrate all of the related fields from the alias objects to the
    primary object.
    
    Usage:
    from django.contrib.auth.models import User
    primary_user = User.objects.get(email='good_email@example.com')
    duplicate_user = User.objects.get(email='good_email+duplicate@example.com')
    merge_model_objects(primary_user, duplicate_user)
    """
    if not isinstance(alias_objects, list):
        alias_objects = [alias_objects]
    
    # check that all aliases are the same class as primary one and that
    # they are subclass of model
    primary_class = primary_object.__class__
    
    if not issubclass(primary_class, models.Model):
        raise TypeError('Only django.db.models.Model subclasses can be merged')
    
    for alias_object in alias_objects:
        if not isinstance(alias_object, primary_class):
            raise TypeError('Only models of same class can be merged')
    
    # Get a list of all GenericForeignKeys in all models
    # TODO: this is a bit of a hack, since the generics framework should provide a similar
    # method to the ForeignKey field for accessing the generic related fields.
    generic_fields = []
    for model in models.get_models():
        for field_name, field in filter(lambda x: isinstance(x[1], GenericForeignKey), model.__dict__.iteritems()):
            generic_fields.append(field)
            
    blank_local_fields = set([field.attname for field in primary_object._meta.local_fields if getattr(primary_object, field.attname) in [None, '']])
    
    # Loop through all alias objects and migrate their data to the primary object.
    for alias_object in alias_objects:
        # Migrate all foreign key references from alias object to primary object.
        for related_object in alias_object._meta.get_all_related_objects():
            # The variable name on the alias_object model.
            alias_varname = related_object.get_accessor_name()
            # The variable name on the related model.
            obj_varname = related_object.field.name
            try:
                related_objects = getattr(alias_object, alias_varname)
                for obj in related_objects.all():
                    primary_objects = getattr(primary_object, alias_varname)
                    found = [hit for hit in primary_objects.all() if hit.equals(obj)]
                    if not found:
                        setattr(obj, obj_varname, primary_object)
                        obj.save()
            except Exception as e:
                pass # didn't have any of that related object

        # Migrate all many to many references from alias object to primary object.
        for related_many_object in alias_object._meta.get_all_related_many_to_many_objects():
            alias_varname = related_many_object.get_accessor_name()
            obj_varname = related_many_object.field.name
            
            if alias_varname is not None:
                # standard case
                related_many_objects = getattr(alias_object, alias_varname).all()
            else:
                # special case, symmetrical relation, no reverse accessor
                related_many_objects = getattr(alias_object, obj_varname).all()
            for obj in related_many_objects.all():
                getattr(obj, obj_varname).remove(alias_object)
                getattr(obj, obj_varname).add(primary_object)

        # Migrate all generic foreign key references from alias object to primary object.
        for field in generic_fields:
            filter_kwargs = {}
            filter_kwargs[field.fk_field] = alias_object._get_pk_val()
            filter_kwargs[field.ct_field] = field.get_content_type(alias_object)
            for generic_related_object in field.model.objects.filter(**filter_kwargs):
                setattr(generic_related_object, field.name, primary_object)
                generic_related_object.save()
                
        # Try to fill all missing values in primary object by values of duplicates
        filled_up = set()
        for field_name in blank_local_fields:
            val = getattr(alias_object, field_name) 
            if val not in [None, '']:
                setattr(primary_object, field_name, val)
                filled_up.add(field_name)
        blank_local_fields -= filled_up
            
        if not keep_old:
            alias_object.delete()
    if save:
        primary_object.save()
    return primary_object