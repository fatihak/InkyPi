from plugins.base_plugin.base_plugin import BasePlugin
import feedparser
import time
import logging

logger = logging.getLogger(__name__)

class RSSReader(BasePlugin):
    def get_feed(self,feed_url,timef_str):
        f=feedparser.parse(feed_url)
        c=[]
        for i in f.entries[0:5]:
            c.append({'title': i.title,'summary': i.summary, 'time':time.strftime(timef_str,i.published_parsed)})  
        return c

#    def generate_settings_template(self):
#        template_params = super().generate_settings_template()
#        template_params['URL'] = self.get_custom_variable()
#        template_params['timef_str'] = self.get_custom_variable()
#        template_params['style_settings'] = True
#        return template_params
    
    def generate_image(self, settings, device_config):

        title = settings.get("title")

        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]
        logger.info(settings)
        image_template_params = {
            "title": title,
            "content": self.get_feed(settings.get('URL'),settings.get('timef_str')),
            "plugin_settings": settings
        }
        logger.info(image_template_params)

        image = self.render_image(dimensions, "rss_reader.html", "rss_reader.css", image_template_params)

        return image