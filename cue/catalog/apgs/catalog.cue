package apgs

import (
	"manifest.management/schema"
)

application_groups: [string]: schema.#ApplicationGroup
application_groups: {}

namespaces: [string]: schema.#Namespace
namespaces: {}

gateways: [string]: schema.#Gateway
gateways: {}

http_routes: [string]: schema.#HTTPRoute
http_routes: {}

services: [string]: schema.#Service
services: {}

service_defaults: [string]: schema.#ServiceDefaults
service_defaults: {}
