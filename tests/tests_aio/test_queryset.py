import random

import pytest
from bson import ObjectId

from yadm import fields
from yadm.documents import Document
from yadm.results import UpdateResult, RemoveResult
from yadm.queryset import NotFoundError


class Doc(Document):
    __collection__ = 'testdocs'
    i = fields.IntegerField
    s = fields.StringField


@pytest.fixture
def qs(loop, db):
    async def fixture():
        for n in range(10):
            await db.db.testdocs.insert({
                'i': n,
                's': 'str({})'.format(n),
            })

    loop.run_until_complete(fixture())
    return db.get_queryset(Doc)


def test_aiter(loop, qs):
    async def test():
        n = 0
        async for doc in qs:
            n += 1
            assert isinstance(doc, Doc)
            assert isinstance(doc.id, ObjectId)

        assert n == 10

    loop.run_until_complete(test())


@pytest.mark.parametrize('slice, result', [
    (slice(None, 2), [6, 7]),
    (slice(2, None), [8, 9]),
    (slice(1, 3), [7, 8]),
    (slice(100, 300), []),
    (slice(None, -3), TypeError),
    (slice(-3, None), TypeError),
    (slice(-3, -1), TypeError),
    (slice(None, None, 2), TypeError),
])
def test_slice(loop, qs, slice, result):
    async def test(qs=qs):
        if isinstance(result, type) and issubclass(result, Exception):
            with pytest.raises(result):
                qs = qs.find({'i': {'$gte': 6}}).sort(('i', 1))[slice]
        else:
            qs = qs.find({'i': {'$gte': 6}}).sort(('i', 1))[slice]
            docs = []
            async for doc in qs:
                docs.append(doc)

            assert [d.i for d in docs] == result

    loop.run_until_complete(test())


def test_get_one(loop, qs):
    async def test(qs=qs):
        qs = qs.find({'i': {'$gte': 6}}).sort(('i', 1))
        doc = await qs[1]
        assert doc.i == 7

    loop.run_until_complete(test())


def test_get_one__index_error(loop, qs):
    async def test(qs=qs):
        qs = qs.find({'i': {'$gte': 6}}).sort(('i', 1))
        with pytest.raises(IndexError):
            await qs[100]

    loop.run_until_complete(test())


def test_count(loop, qs):
    async def test(qs=qs):
        qs = qs.find({'i': {'$gte': 6}})
        assert await qs.count() == 4

    loop.run_until_complete(test())


def test_find_one__query(loop, qs):
    async def test():
        doc = await qs.find_one({'i': 7})
        assert isinstance(doc, Doc)
        assert hasattr(doc, 'i')
        assert doc.i == 7

    loop.run_until_complete(test())


def test_find_one__oid(loop, qs):
    async def test():
        doc = await qs[3]
        res_doc = await qs.find_one(doc.id)
        assert isinstance(res_doc, Doc)
        assert res_doc.id == doc.id
        assert res_doc.i == doc.i

    loop.run_until_complete(test())


def test_find_one__nf(loop, qs):
    async def test():
        res = await qs.find_one({'i': 100500})
        assert res is None

    loop.run_until_complete(test())


def test_find_one__nf_exc(loop, qs):
    class SimpleException(Exception):
        pass

    async def test():
        with pytest.raises(SimpleException):
            await qs.find_one({'i': 100500}, exc=SimpleException)

    loop.run_until_complete(test())


def test_update(loop, db, qs):
    async def test():
        result = await (qs.find({'i': {'$gte': 6}})
                          .update({'$set': {'s': 'test'}}))

        assert isinstance(result, UpdateResult)
        assert result
        assert result.matched == result.modified == int(result) == 4
        assert result.upserted == 0

        assert (await db.db.testdocs.count()) == 10
        assert {d['i'] async for d in db.db.testdocs.find()} == set(range(10))
        assert (await db.db.testdocs.find({'s': 'test'}).count()) == 4

        async for doc in db.db.testdocs.find({'i': {'$lt': 6}}):
            assert doc['s'] != 'test'
            assert doc['s'].startswith('str(')

        async for doc in db.db.testdocs.find({'i': {'$gte': 6}}):
            assert doc['s'] == 'test'

    loop.run_until_complete(test())


def test_find_and_modify(loop, db, qs):
    async def test():
        doc = await qs.find({'i': 6}).find_and_modify({'$set': {'s': 'test'}})

        assert (await db.db.testdocs.count()) == 10
        assert {d['i'] async for d in db.db.testdocs.find()} == set(range(10))
        assert (await db.db.testdocs.find({'s': 'test'}).count()) == 1
        assert (await db.db.testdocs.find_one({'i': 6}))['s'] == 'test'

        assert isinstance(doc, Document)
        assert doc.i == 6
        assert doc.s == 'str(6)'

    loop.run_until_complete(test())


def test_remove(loop, db, qs):
    async def test():
        result = await qs.find({'i': {'$gte': 6}}).remove()

        assert isinstance(result, RemoveResult)
        assert result
        assert result.removed == int(result) == 4

        assert (await qs.count()) == 6
        assert {d.i async for d in qs} == set(range(6))

        assert await db.db.testdocs.count() == 6
        assert {d['i'] async for d in db.db.testdocs.find()} == set(range(6))

    loop.run_until_complete(test())


def test_distinct(loop, db, qs):
    async def test():
        res = await qs.distinct('i')
        assert isinstance(res, list)
        assert len(res) == len(set(res))

        await db.insert(Doc(i=3))
        await db.insert(Doc(i=4))
        await db.insert(Doc(i=10))

        res = await qs.distinct('i')
        assert len(res) == len(set(res))

    loop.run_until_complete(test())


def test_ids(loop, qs):
    async def test():
        res = [i async for i in qs.ids()]
        assert len(res) == 10
        for i in res:
            assert isinstance(i, ObjectId)

    loop.run_until_complete(test())


def test_bulk(loop, qs):
    async def test():
        bulk = await qs.find({'i': {'$gte': 6}}).bulk()
        assert isinstance(bulk, dict)
        assert len(bulk), 4
        assert isinstance(list(bulk)[0], ObjectId)
        assert isinstance(list(bulk.values())[0], Doc)
        _id = list(bulk)[0]
        assert bulk[_id].id == _id
        assert {d.i for d in bulk.values()} == {6, 7, 8, 9}

    loop.run_until_complete(test())


class TestFindIn:
    @pytest.fixture(autouse=True)
    def ids(self, loop, qs):
        async def fixture():
            ids = [doc.id async for doc in qs]
            random.shuffle(ids)
            return ids

        return loop.run_until_complete(fixture())

    def test_simple(self, loop, qs, ids):
        async def test():
            result = [getattr(doc, 'id', doc)
                      async for doc in qs.find_in(ids)]

            assert result == ids

        loop.run_until_complete(test())

    def test_skip(self, loop, qs, ids):
        async def test():
            ids.append('NotExistId')
            result = [doc.id async for doc in qs.find_in(ids)]
            assert result == ids[:-1]

        loop.run_until_complete(test())

    def test_none(self, loop, qs, ids):
        async def test():
            index = random.randrange(len(ids))
            ids[index] = 'NotExistId'
            result = [getattr(doc, 'id', doc)
                      async for doc in qs.find_in(ids, not_found='none')]

            ids[index] = None
            assert result == ids

        loop.run_until_complete(test())

    def test_exception(self, loop, qs, ids):
        async def test():
            [getattr(doc, 'id', doc)
             async for doc in qs.find_in(ids, not_found='error')]

            with pytest.raises(NotFoundError):
                ids.append('NotExistId')
                [getattr(doc, 'id', doc)
                 async for doc in qs.find_in(ids, not_found='error')]

        loop.run_until_complete(test())

    def test_copy_id(self, loop, qs, ids):
        async def test():
            ids.append(ids[0])
            result = [getattr(doc, 'id', doc)
                      async for doc in qs.find_in(ids)]

            assert result == ids

        loop.run_until_complete(test())
