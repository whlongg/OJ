from django.test import TestCase, RequestFactory
from judge.views.problem import ProblemList
from judge.models import Problem, Submission, Profile, ProblemType, ProblemGroup, Language
from django.contrib.auth.models import User
from django.db.models import QuerySet

class ProblemListOrderingTestCase(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(username='testuser', password='password')
        self.profile = Profile.objects.create(user=self.user)
        
        # Create types
        self.type_a, _ = ProblemType.objects.get_or_create(name='A', defaults={'full_name': 'Type A'})
        self.type_b, _ = ProblemType.objects.get_or_create(name='B', defaults={'full_name': 'Type B'})
        self.group, _ = ProblemGroup.objects.get_or_create(name='G', defaults={'full_name': 'Group'})
        self.lang, _ = Language.objects.get_or_create(key='PY3', defaults={'name': 'Python 3'})

        # Create problems
        self.p1 = Problem.objects.create(code='p1', name='Problem 1', group=self.group, points=100, time_limit=1, memory_limit=1024)
        self.p2 = Problem.objects.create(code='p2', name='Problem 2', group=self.group, points=100, time_limit=1, memory_limit=1024)
        self.p3 = Problem.objects.create(code='p3', name='Problem 3', group=self.group, points=100, time_limit=1, memory_limit=1024)
        
        self.p1.allowed_languages.add(self.lang)
        self.p2.allowed_languages.add(self.lang)
        self.p3.allowed_languages.add(self.lang)

        # Add types
        self.p1.types.add(self.type_a)
        self.p3.types.add(self.type_b)
        # p2 has no type

        # Create submissions
        # p1: Solved
        Submission.objects.create(user=self.profile, problem=self.p1, result='AC', points=100, language=self.lang)
        # p2: Attempted but not solved
        Submission.objects.create(user=self.profile, problem=self.p2, result='WA', points=0, language=self.lang)
        # p3: Not attempted

    def test_sort_by_solved(self):
        view = ProblemList()
        request = self.factory.get('/?sort=solved')
        request.user = self.user
        request.profile = self.profile
        request.session = {}
        request.LANGUAGE_CODE = 'en'
        view.request = request
        view.kwargs = {}
        view.setup_problem_list(request)
        view.order = 'solved' # Mock QueryStringSortMixin behavior
        
        queryset = Problem.objects.all()
        sorted_qs = view.order_queryset(queryset)
        
        # Verify order: Unsolved (-1) -> Attempted (0) -> Solved (1)
        # Default is ascending
        expected_ids = [self.p3.id, self.p2.id, self.p1.id]
        result_ids = [p.id for p in sorted_qs]
        self.assertEqual(result_ids, expected_ids)

        # Reverse order: Solved -> Attempted -> Unsolved
        view.order = '-solved'
        sorted_qs = view.order_queryset(queryset)
        expected_ids_desc = [self.p1.id, self.p2.id, self.p3.id]
        result_ids_desc = [p.id for p in sorted_qs]
        self.assertEqual(result_ids_desc, expected_ids_desc)

    def test_sort_by_type(self):
        view = ProblemList()
        # show_types must be enabled
        request = self.factory.get('/?sort=type&show_types=1')
        request.user = self.user
        request.profile = self.profile
        request.session = {}
        request.LANGUAGE_CODE = 'en'
        view.request = request
        view.kwargs = {}
        view.setup_problem_list(request)
        view.order = 'type' # Mock QueryStringSortMixin behavior
        
        queryset = Problem.objects.all().prefetch_related('types')
        sorted_qs = view.order_queryset(queryset)
        
        # Order: '' (p2), 'Type A' (p1), 'Type B' (p3)
        expected_ids = [self.p2.id, self.p1.id, self.p3.id]
        result_ids = [p.id for p in sorted_qs]
        self.assertEqual(result_ids, expected_ids)
        
        # Reverse
        view.order = '-type'
        sorted_qs = view.order_queryset(queryset)
        expected_ids_desc = [self.p3.id, self.p1.id, self.p2.id]
        result_ids_desc = [p.id for p in sorted_qs]
        self.assertEqual(result_ids_desc, expected_ids_desc)

    def test_is_queryset(self):
        view = ProblemList()
        request = self.factory.get('/?sort=solved')
        request.user = self.user
        request.profile = self.profile
        request.session = {}
        request.LANGUAGE_CODE = 'en'
        view.request = request
        view.kwargs = {}
        view.setup_problem_list(request)
        view.order = 'solved'
        
        queryset = Problem.objects.all()
        sorted_qs = view.order_queryset(queryset)
        
        self.assertIsInstance(sorted_qs, QuerySet)
        
        # Test type sort returns QuerySet
        request = self.factory.get('/?sort=type&show_types=1')
        request.user = self.user
        request.profile = self.profile
        request.session = {'show_types': True}
        request.LANGUAGE_CODE = 'en'
        view.request = request
        view.setup_problem_list(request)
        view.order = 'type'
        
        queryset = Problem.objects.all().prefetch_related('types')
        sorted_qs = view.order_queryset(queryset)
        self.assertIsInstance(sorted_qs, QuerySet)
