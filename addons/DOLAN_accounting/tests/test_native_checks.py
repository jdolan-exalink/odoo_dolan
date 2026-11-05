"""Run native check scenarios with the source locale their message assertions expect.

No CE test code is changed. The es_AR default remains tested in DOLAN_base.
"""
from odoo.tests import tagged
from odoo.addons.l10n_latam_check.tests.test_own_checks import TestOwnChecks as _OwnChecks
from odoo.addons.l10n_latam_check.tests.test_third_party_checks import TestThirdChecks as _ThirdChecks


class _SourceLocale:
    allow_inherited_tests_method = True

    @classmethod
    def default_env_context(cls):
        return {**super().default_env_context(), 'lang': 'en_US'}

    @classmethod
    def setup_independent_user(cls):
        user = super().setup_independent_user()
        user.lang = 'en_US'
        return user


@tagged('post_install', '-at_install')
class TestNativeOwnChecks(_SourceLocale, _OwnChecks):
    pass


@tagged('post_install', '-at_install')
class TestNativeThirdPartyChecks(_SourceLocale, _ThirdChecks):
    pass
