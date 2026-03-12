from locust import HttpUser, between, task


class DashboardUser(HttpUser):
    weight = 3
    wait_time = between(2, 5)

    @task
    def dashboard_overview(self):
        self.client.get("/api/v1/dashboard/overview", params={"preset": "7d"})

    @task
    def datacenters_summary(self):
        self.client.get("/api/v1/datacenters/summary", params={"preset": "7d"})


class DetailUser(HttpUser):
    weight = 2
    wait_time = between(3, 8)

    @task
    def datacenter_detail_7d(self):
        self.client.get("/api/v1/datacenters/DC11", params={"preset": "7d"})

    @task
    def datacenter_detail_30d(self):
        self.client.get("/api/v1/datacenters/DC11", params={"preset": "30d"})


class CustomerUser(HttpUser):
    weight = 1
    wait_time = between(5, 10)

    @task
    def customers(self):
        self.client.get("/api/v1/customers")

    @task
    def customer_resources(self):
        self.client.get("/api/v1/customers/Boyner/resources", params={"preset": "7d"})


class HealthCheckUser(HttpUser):
    weight = 1
    wait_time = between(1, 2)

    @task
    def health(self):
        self.client.get("/health")
