"""The initial HTML must expose one authentication form even without JavaScript."""
from html.parser import HTMLParser
import pytest

class Panes(HTMLParser):
    def __init__(self):
        super().__init__(); self.panes={}
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if attrs.get('id') in ('login-pane','signup-pane'):
            self.panes[attrs['id']]=attrs

@pytest.mark.parametrize('query,active',[('', 'login-pane'),('?mode=signup','signup-pane'),('?mode=unknown','login-pane')])
def test_initial_html_has_only_one_exposed_form(client,query,active):
    response=client.get('/login'+query)
    assert response.status_code==200
    parsed=Panes();parsed.feed(response.get_data(as_text=True))
    assert len(parsed.panes)==2
    for name,attrs in parsed.panes.items():
        assert ('hidden' not in attrs)==(name==active)
        assert ('inert' not in attrs)==(name==active)
