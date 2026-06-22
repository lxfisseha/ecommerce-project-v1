#  # we use requests library for the samples
#     import requests
#     # session object
#     session = requests.Session()
#     # base url
#     base_url = 'https://api.afromessage.com/api/send'
#     # api token
#     token = 'YOUR_TOKEN'
#     # header
#     headers = {'Authorization': 'Bearer ' + token}
#     # request parameters
#     callback = 'YOUR_CALLBACK'
#     to = 'YOUR_RECIPIENT'
#     message = 'YOUR_MESSAGE'
#     from = 'YOUR_IDENTIFIER_ID'
#     sender = 'YOUR_SENDER_NAME'
#     # final url
#     url = '%s?from=%s&sender=%s,to=%s&message=%s&callback=%s' % (base_url,from,sender,to, message, callback)
#     # make request
#     result = session.get(url, headers=headers)
#     # check result
#     if result.status_code == 200:
#         # request is success. inspect the json object for the value of `acknowledge`
#         json = result.json()
#         if json['acknowledge'] == 'success':
#             # do success
#             print 'api success'
#         else:
#             # do failure
#             print 'api error'
#     else:
#         # anything other than 200 goes here.
#         print 'http error ... code: %d , msg: %s ' % (result.status_code, result.content)
