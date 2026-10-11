DOMAIN = "icelake"

CONF_ENDPOINT = "endpoint"
CONF_CLIENT_ID = "client_id"
CONF_API_KEY = "api_key"
CONF_SEND_INTERVAL = "send_interval"
CONF_SOURCE_ID = "source_id"
CONF_INCLUDE_DOMAINS = "include_domains"
CONF_EXCLUDE_DOMAINS = "exclude_domains"
CONF_INCLUDE_ENTITIES = "include_entities"
CONF_EXCLUDE_ENTITIES = "exclude_entities"

DEFAULT_SEND_INTERVAL = 30
DEFAULT_SOURCE_ID = "homeassistant"

# Retry with exponential backoff when Icelake is temporarily unavailable
RETRY_BASE_DELAY = 5  # seconds, delay after the first failed attempt
RETRY_MAX_DELAY = 300  # seconds, upper bound for the backoff delay
REQUEST_TIMEOUT = 30  # seconds
MAX_BUFFER_SAMPLES = 100_000  # oldest samples are dropped beyond this
MAX_SAMPLES_PER_REQUEST = 10_000
