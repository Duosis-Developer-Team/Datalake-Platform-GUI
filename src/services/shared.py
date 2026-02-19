# Singleton DatabaseService instance.
# Import this module in every page instead of creating a new DatabaseService().
# Guarantees a single connection pool and a shared cache across all pages.
#
# Usage:
#   from src.services.shared import service
#   data = service.get_dc_details("DC11")

from src.services.db_service import DatabaseService

service: DatabaseService = DatabaseService()
