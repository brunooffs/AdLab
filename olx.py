# Ads Moderation 
# Scenario Background 
# You're working at a startup, a digital advertising platform that serves millions of ads daily across various websites. The company needs a robust content moderation system to ensure ads comply with platform policies before going live.
# The interviewer acts as a product manager of your team and as a fellow engineer. Approach this interview just like any pair programming session at work, collaborating with your colleagues and using any online resources (except AI assistants) to arrive at a working piece of software that solves a problem. Use this pair programming session as an opportunity to mentor and guide your interviewer.
# Create the necessary data structures
# Each ad should include: unique identifier, email (of the seller), title, description, images (each image has a unique identifier and URL)
import re

class content_ad:
    
    def __init_ (seller_id, ad_id, email, title, description, images:list(image)):
        self.seller_id = seller_id
        self.ad_id = ad_id
        self.email = email
        self.title = title
        self.description = description
        self.image_batch = images



    def add_moderation():


    def check_title_description():

        extract_phone_number_pattern = "\\+?[1-9][0-9]{7,14}"

        clean_title = re.findall(extract_phone_number_pattern, self.title)

        clean_description = re.findall(extract_phone_number_pattern, self.description)

        if not clean_title:
            return False
        else:
            return True




class image:
    def __init__(url, uuid):
        self.raw_url = url
        self.u_id = uuid





