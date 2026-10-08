"""Transaction boundaries shared by canonical financial commands."""
from functools import wraps
from inspect import signature


def serialized(command):
    """Serialize money state changes in the caller's transaction, including SQLite.

    A deliberately coarse DB lock prevents refund/hold/transfer races. Provider
    dispatch is a separate durable command; no network call holds this lock.
    """
    sig = signature(command)

    @wraps(command)
    def run(*args, **kwargs):
        from services import flow_of_funds as flow
        bound = sig.bind(*args, **kwargs)
        conn = bound.arguments.get('conn')
        own = conn is None
        conn = conn or flow.get_db_connection()
        try:
            flow.ensure_flow_schema(conn)
            conn.execute("UPDATE flow_mutex SET revision=revision+1 WHERE id=1")
            bound.arguments['conn'] = conn
            result = command(*bound.args, **bound.kwargs)
            if own:
                conn.commit()
            return result
        except Exception:
            if own:
                conn.rollback()
            raise
        finally:
            if own:
                conn.close()
    return run
