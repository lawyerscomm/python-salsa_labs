#!/usr/bin/python3

import requests
import argparse
import getpass
import json
import csv
import urllib
import os.path
import tempfile
import json
import copy
import sys
import xml.etree.ElementTree as ET

def get_arg_join (arg_dict):
    arg_list = ['%s=%s' % (k,urllib.parse.quote_plus(v, '')) for k,v in arg_dict.items()]
    return '&'.join(arg_list)

def url_arg_join (base_url, arg_dict):
    return base_url + get_arg_join(arg_dict)

def auth (API_URL, args):
    auth_frag = '/api/authenticate.sjs?json&'
    auth_url = API_URL + auth_frag
    auth_args = {'organization_KEY': '5957'}

    s = requests.Session()
    
    if not args.email:
        auth_args['email'] = input('Salsa email address: ')
    else:
        auth_args['email'] = args.email
    
    auth_args['password'] = getpass.getpass()

    url = url_arg_join(auth_url, auth_args)

    r = s.get(url, verify=False)

    try:
        rjson = r.json()
    except ValueError:
        print('Malformed response from server during authentication. Exiting.')
        exit(1)

    try:
        if rjson['status'] == 'success':
            session_cookie = dict(jsessionid = rjson['jsessionid'])
        else:
            print('Authentication failure. Wrong email address or password.')
            exit(0)
    except KeyError:
        print('Malformed response from server during authentication. Exiting.')
        exit(1)

    return s

def getObject (API_URL, session, args, objects_filename):
    getObject_frag = '/api/getObject.sjs?json&'
    getObject_url = API_URL + getObject_frag

    url = url_arg_join(getObject_url, args)

    r = session.get(url, verify=False)
    rjson = r.json()

    with open(objects_filename, 'w', newline='') as f:
        writer = csv.DictWriter(f, rjson.keys(), dialect='excel')
        writer.writeheader()
        writer.writerow(rjson)
    

def describe (API_URL, session, args):
    describe_frag = '/api/describe2.sjs?json&'
    describe_url = API_URL + describe_frag

    url = url_arg_join(describe_url, args)

    r = session.get(url, verify=False)

    try:
        rjson = r.json()
    except ValueError:
        print('Malformed response from server during describe. Exiting.')
        exit(1)

    return rjson

def delete (API_URL, session, args):

    # In JSON mode, delete works like describe. Feature!
    # In XML mode, it returns malformed XML:
    # Failure:
#    <?xml version="1.0"?>
#	<response><error table="event" key="423595" exc="java.lang.Exception: You do not have access to this row:423595">You do not have access to this row:423595</error>
#</response>
    # Success:
#<?xml version="1.0"?>
#	<response><success table="event" key="423596">Deleted entry 423596</success>
#</response>

    delete_frag = '/delete?xml&'
    delete_url = API_URL + delete_frag

    url = url_arg_join(delete_url, args)

    r = session.get(url, verify=False)

    #except xml.etree.ElementTree.ParseError:
    try:
        root = ET.fromstring(r.text)
    except ET.ParseError:
        sys.exit('Malformed response during delete. Exiting.')
    
    try:
        response = root[0]
    except IndexError:
        sys.exit('Malformed XML response during delete. Exiting.')

    try:
        row = {
            'result': response.tag,
            'object': response.attrib['table'],
            'key': response.attrib['key'],
            'message': response.text,
        }
    except (AttributeError, KeyError):
        sys.exit('Seriously malformed XML response during delete. Exiting.')

    return row

def save (API_URL, session, args):

    # Salsa responses to save are horribly malformed in both xml and json, for some reason. They actually look like this:    
#    salsajson = '''<br/>No captcha on this form, continuing.<br/>
#<!-- A feature has been hidden because you are not logged in --><!-- A feature has been hidden because you are not logged in --><!-- A feature has 
#been hidden because you are not logged in -->                                                                                                     
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#[{"object":"event","key":"423498","result":"success","messages":[]}]'''

    # Errors:
    # [{"object":"null","key":"0","result":"error","messages":["There was a problem with your submission.  No object was specified."]}]

    save_frag = '/save?json&'
    save_url = API_URL + save_frag

    url = url_arg_join(save_url, args)
    
    r = session.get(url, verify=False)

    try:
        rjson = json.loads(r.text.split("\n")[-1])[0]
    except ValueError:
        print('Malformed response from server during save. Exiting.')
        exit(1)
   
    return rjson

def main ():

    API_URL = 'https://signup.lawyerscommittee.org'
    
    argparser = argparse.ArgumentParser()
    argparser.add_argument('--delete', action='store_true', default=False, help='Delete records in CSV instead of adding or modifying them.')
    argparser.add_argument('--getobject', action='store_true', default=False, help='Get a single Salsa object by key.')
    argparser.add_argument('--key', help='Salsa object key to get')
    argparser.add_argument('--email', required=True, help='Salsa campaign manager email address')
    argparser.add_argument('--object', required=True, help='Salsa object type. Common objects include: supporter, groups, supporter_groups, event, distributed_event, supporter_event, donation')
    argparser.add_argument('objects_filename', help='CSV file of objects to upload to Salsa')
    args = argparser.parse_args()

    abs_objects_path = os.path.abspath(args.objects_filename)
    objects_base = os.path.basename(abs_objects_path)
    objects_root, objects_ext = os.path.splitext(objects_base)
    objects_dir = os.path.dirname(abs_objects_path)

    obj_KEY = args.object+'_KEY'


    session = auth(API_URL, args)

    if args.getobject:
        getObject(API_URL, session, {'object':args.object, 'key':args.key}, args.objects_filename)
        exit(0)

    description = describe(API_URL, session, {'object': args.object})
    object_fields = frozenset([field['name'] for field in description])

    with open(args.objects_filename, newline='') as f:
        try:
            dialect = csv.Sniffer().sniff(f.read(1024))
            f.seek(0)
        except csv.Error as e:
            sys.exit('Could not sniff CSV for dialect: %s' % (e))

        try:
            if not csv.Sniffer().has_header(f.read(1024)):
                sys.exit('CSV file does not have header row. Exiting.')
            f.seek(0)
        except csv.Error as e:
            sys.exit('Could not sniff header row from CSV: %s' % (e))


        try:
            reader = csv.DictReader(f, dialect=dialect)
        except csv.Error as e:
            sys.exit('Could not get CSV reader from file: %s' % (e))

        csv_fields = set(reader.fieldnames)

        # The fields returned by describe2 are equivalent to those used for API functions EXCEPT 'key'
        # For save, describe2, etc, the object and key are always expressed as ?object=event&key=12345.
        # But describe2 returns 'key' like 'event_KEY'.
        # So, we store the describe2 version in the CSV, and transform it upon read.
        # That way, this subset still passes because csv_fields from the CSV and object_fields from describe2
        # both have obect_KEY, like 'event_KEY'.
        csv_fields.remove('key')

        # GRRRRRRRRR!!!!!!!!!!
        #if not csv_fields.issubset(object_fields):
        #    sys.exit(print(csv_fields - object_fields))
        #    #sys.exit('CSV header contains field names that are not available for Salsa object %s' % (args.object))

        with tempfile.NamedTemporaryFile(mode='w', newline='', suffix=objects_ext, prefix=objects_root+'-', dir=objects_dir, delete=False) as w:

            results_fieldnames = reader.fieldnames[:]
            results_fieldnames.append(obj_KEY)

            try:
                if args.delete:
                    writer = csv.DictWriter(w, fieldnames=['result','object','key','message'], dialect='excel')
                else:
                    writer = csv.DictWriter(w, fieldnames=results_fieldnames, dialect='excel')
            except csv.Error as e:
                sys.exit('Could not get CSV writer from file: %s' % (e))

            try:
                writer.writeheader()
            except csv.Error as e:
                sys.exit('Could not write header to results CSV file: %s' % (e))

            try:
                for row in reader:
                    # Copy the input row to make some changes before saving.
                    obj_args = copy.copy(row)

                    obj_args['object'] = args.object
                    ## Change the key string to just 'key' because that's what the API expects
                    ## ...if we have it because we're modifying existing objects.
                    #if obj_KEY in obj_args.keys():
                    #    obj_args['key'] = obj_args[obj_KEY]
                    # And remove the object's key name as returned from describe2.
                    #obj_args.pop(obj_KEY, None)

                    if args.delete:
                        row = delete(API_URL, session, {'object':args.object, 'key': row[obj_KEY]})
                        print(row['message'])
                    else:
                        rjson = save(API_URL, session, obj_args)
                        
                        # On the flip side, write the returned key to the object's key name.
                        #row[obj_KEY] = rjson['key']
                        
                        if rjson['result'] == 'success':
                            print('Saved %s object %s' % (args.object, rjson['key']))
                        else:
                            for message in rjson['messages']:
                                print(message)

                    try:
                        writer.writerow(row)
                    except csv.Error as e:
                        sys.exit('file {}, line {}: {}'.format(w.name, writer.line_num, e))
                            
            except csv.Error as e:
                sys.exit('file {}, line {}: {}'.format(f.name, reader.line_num, e))

            print('Wrote results to %s' % (w.name))
                

if __name__ == "__main__":
    main()
