from django.test import TestCase
from django.urls import reverse

class SimpleTest(TestCase):
    def test_homepage_status_code(self):
        # Assuming you have a home view at '/'
        response = self.client.get('/redoc')
        self.assertEqual(response.status_code, 200)