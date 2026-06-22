from .fashion import FashionHandler
from .generic_commerce import GenericCommerceHandler
from .license_plate import LicensePlateHandler


DOMAIN_HANDLERS = {
    "generic_commerce": GenericCommerceHandler(),
    "fashion": FashionHandler(),
    "license_plate": LicensePlateHandler(),
}


def get_domain_handler(domain):
    return DOMAIN_HANDLERS.get(str(domain or "").strip()) or DOMAIN_HANDLERS["generic_commerce"]
