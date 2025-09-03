import datetime
import logging
import schedule
import time
import tweepy
from pprint import pformat
from .twitter_config import TwitterConfig

logger = logging.getLogger(__name__)
logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.INFO)

class Twitter:
    """A class for interfacing with the Twitter API using Tweepy.

    Attributes:
        v2api (tweepy.Client): Tweepy client for Twitter API v2.
        user (dict): Authenticated user info.
        username (str): Screen name.
        user_id (str): User id.

    Methods:
        respond_to_key_users(): Respond to tracked users' conversations.
        post_tweet(post_text, in_reply_to_tweet_id, quote_tweet_id):
            Posts a tweet. Returns (ok: bool, tweet_id_or_None, retry_after_seconds_or_None).
    """

    def __init__(
        self,
        consumer_key,
        consumer_secret,
        access_token,
        access_token_secret,
        bearer_token,
        model
    ):
        """
        Initializes the Twitter class with the necessary parameters.
        Sets up the Tweepy client and retrieves the authenticated user's ID.
        """
        logger.info("[TWITTER] Initializing Twitter client...")
        self.v2api = tweepy.Client(
            bearer_token=bearer_token,
            consumer_key=consumer_key,
            consumer_secret=consumer_secret,
            access_token=access_token,
            access_token_secret=access_token_secret,
            return_type=dict
        )

        logger.info("[TWITTER] Starting Twitter client...")
        self.user = self.v2api.get_me()
        self.username = self.user["data"]["username"]
        self.user_id = self.user["data"]["id"]

        self.model = model
        self.config = TwitterConfig()

        # Calculate interval in minutes between runs
        self.interval = 1440.0 / self.config.RUNS_PER_DAY

        logging.info(f"[TWITTER] Connected to twitter user @{self.username} with id {self.user_id}.")

        if not self.config.KEY_USERS:
            raise Exception("[TWITTER] You need to configure your twitter agent's key users")
        if not self.config.RUNS_PER_DAY:
            raise Exception("[TWITTER] You need to configure your twitter agent's runs per day")

    def run(self):
        def job():
            self.respond_to_key_users()
            if self.config.POST_MODE:
                # If POST_MODE is True, generate a post with model
                try:
                    post = self.model.query(self.config.POST_PROMPT) if self.model else None
                    post = (post or "").strip() or "Hello world"
                    self.post_tweet(post)
                except Exception as e:
                    logging.exception(f"[TWITTER] Error generating auto post: {e}")

        job()
        schedule.every(self.interval).minutes.do(job)
        while True:
            schedule.run_pending()
            time.sleep(60)

    def __build_search_query_users(self, key_users):
        """Returns a twitter search query for tweets from a list of users"""
        return "(from:" + " OR from:".join(key_users) + ")"

    def __build_search_query_key_phrase(self):
        """Returns a twitter search query for tweets containing key phrase"""
        return f' "{self.config.KEY_PHRASE}"'

    def __build_search_query_ignore_retweets(self):
        """Returns a twitter search query that ignores retweets"""
        return " -is:retweet"

    def __build_search_query_ignore_quotes(self):
        """Returns a twitter search query that ignores quotes"""
        return " -is:quote"

    def __search_for_relevant_conversations(self, start_time=None):
        """
        Gets tweets from key users or from specific conversations.
        Returns tweets grouped by conversation_id.
        """
        query = self.__build_search_query_users(self.config.KEY_USERS)
        query += self.__build_search_query_ignore_retweets()
        if self.config.KEY_PHRASE:
            query += self.__build_search_query_key_phrase()
        if self.config.QUOTE_MODE:
            query += self.__build_search_query_ignore_quotes()
        logging.debug(f"[TWITTER] Twitter search query: {query}")

        response = self.v2api.search_recent_tweets(
            query=query,
            start_time=start_time,
            tweet_fields=["created_at","author_id","conversation_id", "public_metrics"],
            expansions=["author_id","referenced_tweets.id"]
        )
        logging.debug(f"[TWITTER] Twitter search results: {response}")

        if not response.get("data", False):
            return {}

        authors = {user["id"]: user["username"] for user in response["includes"]["users"]}
        tweets = {tweet["id"]: tweet for tweet in response["data"]}

        conversations = {}
        for tweet in tweets.values():
            author_id = tweet["author_id"]
            conversation_id = tweet["conversation_id"]

            referenced_tweets = tweet.get("referenced_tweets", [])
            if referenced_tweets:
                reply = referenced_tweets[0]["type"] == "replied_to"
                replied_to = tweets.get(referenced_tweets[0]["id"], False)
                if reply and ((not replied_to) or (not replied_to["author_id"] == author_id)):
                    continue

            authors_conversations = conversations.get(author_id, {})
            conversation = authors_conversations.get(conversation_id, [])
            conversation.append(
                {
                    "id": tweet["id"],
                    "text": tweet["text"],
                    "author_id": tweet["author_id"],
                    "author": authors[tweet["author_id"]],
                    "created_at": tweet["created_at"],
                    "conversation_id": tweet["conversation_id"],
                    "referenced_tweets": referenced_tweets,
                    "public_metrics": tweet["public_metrics"]
                }
            )
            sorted_conversation = sorted(conversation, key=lambda k: k["created_at"])
            authors_conversations[conversation_id] = sorted_conversation
            conversations[author_id] = authors_conversations

        return conversations

    def __get_relevant_conversations(self):
        """Fetches all conversations involving key_users in past `interval` minutes"""
        logging.debug(f"[TWITTER] Key users: {self.config.KEY_USERS}")
        logging.info(f"[TWITTER] Fetching relevant conversations from past {self.interval} minutes...")

        start_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=self.interval)
        relevant_conversations = self.__search_for_relevant_conversations(start_time=start_time)

        logging.info(f"[TWITTER] Relevant conversations:")
        if relevant_conversations:
            logging.info(pformat(relevant_conversations))
        return relevant_conversations

    def __respond_to_conversation(self, conversation, response):
        """Uses model to respond to conversation"""
        logging.debug(pformat(conversation))
        first_tweet_id = conversation[0]["id"]
        last_tweet_id = conversation[-1]["id"]
        reply_tweet_id = last_tweet_id if not self.config.QUOTE_MODE else None
        quote_tweet_id = first_tweet_id if self.config.QUOTE_MODE else None
        self.post_tweet(response, reply_tweet_id, quote_tweet_id)

    def respond_to_key_users(self):
        """Responds to tweets by key users"""
        logging.info(f"[TWITTER] Responding to key users...")
        relevant_conversations = self.__get_relevant_conversations()
        response_count = 0

        if not relevant_conversations:
            logging.info(f"[TWITTER] No conversations to respond to.")
            return

        for user_conversations in relevant_conversations.values():
            for conversation in user_conversations.values():
                if response_count >= self.config.RESPONSES_PER_RUN:
                    logging.info(f"[TWITTER] Responded to max responses.")
                    break

                conversation_id = conversation[0]["conversation_id"]
                logging.info(f"[TWITTER] Responding to conversation {conversation_id}...")

                prompt = f"{self.config.RESPONSE_PROMPT} {conversation}"
                try:
                    response = self.model.query(prompt)
                    logging.info(f"[TWITTER] Response: {response}")
                    logging.info(f"[TWITTER] Posting response...")
                    self.__respond_to_conversation(conversation, response)
                    response_count += 1
                except Exception as e:
                    logging.exception(f"[TWITTER] Error responding to conversation {conversation_id}. {e}")

        logging.info(f"[TWITTER] Successfully responded to relevant conversations.")

    def post_tweet(self, post_text, in_reply_to_tweet_id=None, quote_tweet_id=None):
        """Posts a new tweet or a reply to the specified tweet.
        Returns: (ok: bool, tweet_id_or_None, retry_after_seconds_or_None)
        """
        try:
            response = self.v2api.create_tweet(
                in_reply_to_tweet_id=in_reply_to_tweet_id,
                quote_tweet_id=quote_tweet_id,
                text=post_text
            )
            return (True, response["data"]["id"], None)
        except Exception as e:
            # Handle rate limit 429 with best-effort Retry-After extraction
            if isinstance(e, tweepy.errors.TooManyRequests):
                retry_after = None
                try:
                    headers = getattr(e, "response", None).headers or {}
                    # Normalize keys to lower for lookup
                    low = {k.lower(): v for k, v in headers.items()}
                    if "retry-after" in low:
                        retry_after = int(low["retry-after"])
                    elif "x-rate-limit-reset" in low:
                        reset_at = int(low["x-rate-limit-reset"])
                        retry_after = max(0, reset_at - int(time.time()))
                except Exception:
                    pass
                logging.warning("[TWITTER] Rate limited (429). Retry-After=%s", retry_after)
                return (False, None, retry_after)

            logging.exception(f"[TWITTER] Error posting tweet: {e}")
            return (False, None, None)
