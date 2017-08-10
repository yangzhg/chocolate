from collections import Mapping, Sequence
from numbers import Number

import pandas

from .space import Space


class Connection(object):
    """Abstract connection class that defines the database connection API.
    """
    def lock(self):
        raise NotImplementedError

    def all_results(self):
        raise NotImplementedError

    def find_results(self, filter):
        raise NotImplementedError

    def insert_result(self, entry):
        raise NotImplementedError

    def update_result(self, entry, value):
        raise NotImplementedError

    def count_results(self):
        raise NotImplementedError

    def all_complementary(self):
        raise NotImplementedError

    def insert_complementary(self, document):
        raise NotImplementedError

    def find_complementary(self, filter):
        raise NotImplementedError

    def get_space(self):
        raise NotImplementedError

    def insert_space(self, space):
        raise NotImplementedError

    def clear(self):
        raise NotImplementedError

    def pop_id(self, document):
        raise NotImplementedError

    def results_as_dataframe(self):
        """Compile all the results and transform them using the space specified in the database. It is safe to
        use this method while other experiments are still writing to the database.

        Returns:
            A :class:`pandas.DataFrame` containing all results with its ``"_chocolate_id"`` as ``"id"``,
            their parameters and its loss. Pending results have a loss of :data:`None`.
        """
        with self.lock():
            s = self.get_space()
            results = self.all_results()

        all_results = []
        for r in results:
            result = s([r[k] for k in s.names()])
            # Find all losses
            losses = {k: v for k, v in r.items() if k.startswith("_loss")}
            if all(l is not None for l in losses.values()):
                result.update(losses)

            result["id"] = r["_chocolate_id"]
            all_results.append(result)

        df = pandas.DataFrame.from_dict(all_results)
        df.index = df.id
        df.drop("id", inplace=True, axis=1)
        return df


class SearchAlgorithm(object):
    """Base class for search algorithms. Other than providing the :meth:`update` method
    it ensures the provided space fits with the one int the database.
    """
    def __init__(self, connection, space=None, crossvalidation=None, clear_db=False):
        if space is not None and not isinstance(space, Space):
            space = Space(space)

        self.conn = connection
        with self.conn.lock():
            db_space = self.conn.get_space()

            if space is None and db_space is None:
                raise RuntimeError("The database does not contain any space, please provide one through"
                    "the 'space' argument")

            elif space is not None and db_space is not None:
                if space != db_space and clear_db is False:
                    raise RuntimeError("The provided space and database space are different. To overwrite "
                        "the space contained in the database set the 'clear_db' argument")
                elif space != db_space and clear_db is True:
                    self.conn.clear()
                    self.conn.insert_space(space)

            elif space is not None and db_space is None:
                self.conn.insert_space(space)

            elif space is None and db_space is not None:
                space = db_space

        self.space = space

        self.crossvalidation = crossvalidation
        if self.crossvalidation is not None:
            self.crossvalidation = crossvalidation
            self.crossvalidation.wrap_connection(connection)

    def update(self, token, values):
        """Update the loss of the parameters associated with *token*.

        Args:
            token: A token generated by the sampling algorithm for the current
                parameters
            values: The loss of the current parameter set. The values can be a
                single :class:`Number`, a :class:`Sequence` or a :class:`Mapping`.
                When a sequence is given, the column name is set to "_loss_i" where
                "i" is the index of the value. When a mapping is given, each key
                is prefixed with the string "_loss_".

        """
        if isinstance(values, Sequence):
            values = {"_loss_{}".format(i): v for i, v in enumerate(values)}

        elif isinstance(values, Mapping):
            values = {"_loss_{}".format(k): v for k, v in values.items()}

        elif isinstance(values, Number):
            values = {"_loss": values}

        print(values)
        with self.conn.lock():
            self.conn.update_result(token, values)

    def next(self):
        """Retrieve the next point to evaluate based on available data in the
        database.

        Returns:
            A tuple containing a unique token and a fully qualified parameter set.
        """
        with self.conn.lock():
            if self.crossvalidation is not None:
                reps_token, params = self.crossvalidation.next()
                if reps_token is not None and params is not None:
                    return reps_token, params
                elif reps_token is not None and params is None:
                    token, params = self._next(reps_token)
                    return token, params

            return self._next()

    def _next(self, token=None):
        raise NotImplementedError
