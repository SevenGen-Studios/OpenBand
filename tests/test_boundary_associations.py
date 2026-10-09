import unittest
from tools.reconcile_map_boundaries import boundary_ids


class BoundaryAssociations(unittest.TestCase):
    def test_reserve_number_survives_damaged_authoritative_owner_label(self):
        feature = {'properties': {'ADMIN_LAND_ID': '9648', 'FIRST_NATIONS': 'Tthebatthie Denesulin\ufffd Nation'}}
        self.assertEqual(boundary_ids({'reserves': [{'number': '09648'}]},
                                      {'reserveOwnerNames': ['Tthebatthie Denesųłiné Nation']}, [feature]), ['9648'])

    def test_does_not_assign_unrelated_land(self):
        feature = {'properties': {'ADMIN_LAND_ID': '6704', 'FIRST_NATIONS': 'Athabasca Chipewyan First Nation'}}
        self.assertEqual(boundary_ids({'reserves': [{'number': '09648'}]},
                                      {'reserveOwnerNames': ['Tthebatthie Denesųłiné Nation']}, [feature]), [])

    def test_shared_isc_government_does_not_inherit_boundary(self):
        feature = {'properties': {'ADMIN_LAND_ID': '1', 'FIRST_NATIONS': 'Saddle Lake'}}
        self.assertEqual(boundary_ids({'sharedIscIdentity': True, 'reserves': [{'number': '1'}]}, {}, [feature]), [])
