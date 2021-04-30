"""A Python Pulumi program"""

import pulumi
import pulumi_akamai as akamai

# get information from our config file that is stack specific
# use "pulumi config set <key> [value]" to set the value
# Config is unique per project/stack. 
# To create a new stack in a project use "pulumi stack init" from project dir and select it via "pulumi stack select"
config = pulumi.Config()
group_name = config.require("group_name")
property_name = config.require("property_name")
origin_name = config.require("origin_name")

# check products available on contract
# first list contracts via: akamai pm lc
# lookup product on contract via : akamai pm lp -c <contract_id> 
product = 'dsa'

# engineering code names don't match product names
# below a list of products with their engineering names
# https://registry.terraform.io/providers/akamai/akamai/latest/docs/guides/appendix
products = {
    'dsa': 'prd_Site_Accel',
    'dsd': 'prd_Dynamic_Site_Del',
    'ion': 'prd_Fresca',
    'ion_p': 'prd_SPM'
}

# define the product id you want to use for your property
# this should match the template and cpcode 
# https://registry.terraform.io/providers/akamai/akamai/latest/docs/guides/appendix
product_id = products[product]

# first lookup contract_id and group_id as we need that info for every resource we create
# to lookup available groups use: akamai pm lg
# as we're not waiting for a resource to get provisioned we should just wait for this call
# let see if we can create an edgehostname without the pulumi.Output.from_input() for our first two calls
# return types are "Awaitable" and will not create any resource
contract_id = akamai.get_contracts().contracts[0].contract_id
group_id = akamai.get_group(contract_id=contract_id, group_name=group_name).id

# our pipeline template file created via:
# akamai pipeline np -p <name> dev -g <group> -c <contract> -d <product_id>
# since pulumi_akamai 2.1.0 we need to use property-snippets directory name.
template_file = f"{product}/property-snippets/main.json"

# we tried using apply() with lambda function but then Property resource will fail as rules are empty.
# so we need another project/stack we require a value to be present.
# so let's reference another stack and use apply() to get the value as it's an Output object again
# to check the output "pulumi stack output"
other = pulumi.StackReference("jjgrinwis/cpcode/cpcode")
cpcode_name = other.get_output("cpcode_name").apply(lambda x: f"{x}")
# cpcode_id = other.get_output("cpcode_id").apply(lambda x: x.split('_')[1] )

# as we're out of availble cpcodes on this contract, lets use an existing one
# akamai pm lcp -g <group_id> -c <contract_id>
# https://www.pulumi.com/docs/reference/pkg/akamai/getcpcode/
# using a cpcode from a different pulumi stack
cpcode = akamai.get_cp_code(name=cpcode_name, contract_id=contract_id, group_id=group_id)

# let's check if product_id is part of the cpcode list
# this is not a showstopper but just to make you aware.
if product_id not in cpcode.product_ids:
    error_string = f"{product_id} not part of cpcode {cpcode.name}"
    pulumi.warn(error_string)

# we tried to create a new cpcode resource but that can't be used with our template
# template won't wait for the result so will give an error as cpcode value isn't there yet.
# we can solve that with a lambda but rules will be empty to creating the property will fail.
# left it here to show how to use lambda with apply()
# cpcode = akamai.CpCode(
#     property_name,
#     contract_id=contract_id,
#     group_id=group_id,
#     product=product_id
# )

# def make_template(s):
#     return akamai.get_property_rules_template(
#         template_file=template_file,
#         variables = [{
#           'name':"cpCode",
#           'value': int(s),
#           'type': "number",
#       }]
#     )
# rules = cpcode.id.apply(lambda s: make_template(s.split('_')[1]))
# rules = cpcode.id.apply(lambda s: make_template(s.split('_')[1]).json)

# first create a local template instance via akamai pipeline. 
# akamai pipeline np -p template dev -g <group_id> -c <contract_id> -d <product_id>
# this will create the json templates in the templates folder under template dir.
# https://www.pulumi.com/docs/reference/pkg/akamai/getpropertyrulestemplate/#getpropertyrulestemplatevariable
# using akamai pipeline some default vars have been created like "${env.cpcCde}"
# it's possible to use the variableDefinitions.json and variables.json or define them in the call itself.
# our result is a GetPropertyRulesTemplateResult object with json field with the json config
# as it's not an Output object we can reference the values directly.
property_rules = akamai.get_property_rules_template(
    template_file=template_file,
    variables = [
        {
            'name':"cpCode",
            'value': int(cpcode.id.split('_')[1]),
            'type': "number",
        },
        {
            'name':"originHostname",
            'value': origin_name,
            'type': "string",
        },
        {
            'name':"sureRouteTestObject",
            'value': "/akamai/sure-route-test-object.html",
            'type': "string",
        }
    ]
)

# create a new edgehostname resource on standard TLS (edgesuite.net) with IPv4 and IPv6 (IPV6_COMPLIANCE)
# with standard TLS we don't need to assign a certificate, just add that at a later stage.
# https://www.pulumi.com/docs/reference/pkg/akamai/edgehostname/
# EdgeHostName will return an Output object but won't get removed with a "pulumi destroy" or modified!
# Make sure to select correct product_id that matches with the property_id in the configuration.
edge_hostname = f'{property_name}.edgesuite.net'
edge_host = akamai.EdgeHostName(
    edge_hostname,
    contract_id=contract_id,
    group_id=group_id,
    product_id=product_id,
    edge_hostname=edge_hostname,
    ip_behavior='IPV6_COMPLIANCE'
)

# create our Property resource using our template we've collected before
# https://www.pulumi.com/docs/reference/pkg/akamai/properties/property/
# https://registry.terraform.io/providers/akamai/akamai/latest/docs/resources/property
# using some Output vars from the created edge_host resource so waiting for that.
# hostnames var changed in the Akamai Terraform provider 1.5.1
# hostnames = Optional[pulumi.Input[Sequence[pulumi.Input[pulumi.InputType['PropertyHostnameArgs']]]]
# for the hostname, cert can be DEFAULT or CPS_MANAGED
# for extra debugging:
# TF_LOG=TRACE pulumi up --logtostderr -v=9 2> out.txt
prop = akamai.Property (
    property_name,
    contract_id = contract_id,
    group_id = group_id,
    product_id=product_id,
    name = property_name,
    rules = property_rules.json,
    hostnames = [ 
        {                                     
            "cname_from": property_name,
            "cname_to" : edge_host.edge_hostname,
            "cert_provisioning_type": "CPS_MANAGED"
        }
    ]
)

# looks like we need to activate it before we can make modifications.
# let's activate it on staging and get id and latest_version from created property resource
# https://www.pulumi.com/docs/reference/pkg/akamai/propertyactivation/
prop_staging = akamai.PropertyActivation("propStaging",
    property_id=prop.id,
    contacts=['jgrinwis@akamai.com'],
    version=prop.latest_version)

# you can check the output via "pulumi stack output edge_hostname"
pulumi.export("property", prop.latest_version)