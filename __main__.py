"""A Python Pulumi program"""

import pulumi
import pulumi_akamai as akamai

group_name = "GSS Training Internal-C-1IE2OHM"
cpcode_name = "jgrinwis-pristine"
property_name = "pulumi.grinwis.com"

# check products available on contract via
# akamai pm lp -c <contract_id> 
product = 'dsa'
products = {
    'dsa': 'prd_Site_Accel',
    'dsd': 'prd_Dynamic_Site_Del',
    'ion': 'prd_Fresca',
    'ion_p': 'prd_SPM'
}

# our pipeline template file created via 
# akamai pipeline np -p <name> dev -g <group> -c <contract> -d <product_id>
template_file = "{}/templates/main.json".format(product)

# define the product id you want to use for your property
# this should match the template and cpcode 
# https://registry.terraform.io/providers/akamai/akamai/latest/docs/guides/appendix
product_id = products[product]

# as we're not waiting for a resource to get provisioned we should just wait for this call
# let see if we can create an edgehostname without the pulumi.Output.from_input() for our first two calls
# return types are "Awaitable" and not creating any resource
contract_id = akamai.get_contracts().contracts[0].contract_id
group_id = akamai.get_group(contract_id=contract_id, group_name=group_name).id

# as we're out of availble cpcodes on this contract, lets use an existing one
# $ akamai pm lcp -g grp_67223 -c ctr_C-1IE2OHM
# https://www.pulumi.com/docs/reference/pkg/akamai/getcpcode/
cpcode = akamai.get_cp_code(name=cpcode_name, contract_id=contract_id, group_id=group_id)

# let's check if product_id is part of the cpcode list
# this is not a showstopper but just to make you aware.
if product_id not in cpcode.product_ids:
    error_string = "{} not part of cpcode {}".format(product_id, cpcode.name)
    pulumi.warn(error_string)

# let's get the rules of an existing property, first lookup property_id
# https://www.pulumi.com/docs/reference/pkg/akamai/properties/getproperty/
# https://www.pulumi.com/docs/reference/pkg/akamai/properties/getpropertyrules/
# using this property as an example
# property_id = akamai.get_property(property_name).id
# property_rules = akamai.get_property_rules(contract_id=contract_id, group_id=group_id, property_id=property_id).rules
# print(property_rules)

# first create a local template instance via akamai pipeline. 
# akamai pipeline np -p template dev -g grp_67223 -c ctr_C-1IE2OHM -d prd_Dynamic_Site_Del
# this will create the json templates in the templates folder under template dir.
# https://www.pulumi.com/docs/reference/pkg/akamai/getpropertyrulestemplate/#getpropertyrulestemplatevariable
# using akamai pipeline some default vars have been created like "${env.cpcCde}"
# it's possible to use the variableDefinitions.json and variables.json or define them in the call itself.
# our result is a GetPropertyRulesTemplateResult object with json field with the json config
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
            'value': "netlify.grinwis.com",
            'type': "string",
        },
        {
            'name':"sureRouteTestObject",
            'value': "/akamai/sure-route-test-object.html",
            'type': "string",
        }
    ]
)

# print(property_rules.json)

# create a new edgehostname resource on standard TLS (edgesuite.net) with IPv4 and IPv6 (IPV6_COMPLIANCE)
# with standard TLS we don't need to assign a certificate, just add that at a later stage.
# https://www.pulumi.com/docs/reference/pkg/akamai/edgehostname/
# EdgeHostName will return an Output object but won't get removed with a "pulumi destroy" or modified!
# so make sure to select correct product_id that matches with the property_id in the configuration.
edge_hostname = '{}.edgesuite.net'.format(property_name)
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
# using some Output vars from the created edge_host resource so waiting for that
# we hit issue: https://github.com/pulumi/pulumi-akamai/issues/36
# so we can't use empty behaviors, too strict checking by pulumi.
prop = akamai.Property (
    property_name,
    contract_id = contract_id,
    group_id = group_id,
    product_id=product_id,
    name = property_name,
    rules = property_rules.json,
    hostnames = {
        property_name: edge_host.edge_hostname
    }
)

# you can check the output via "pulumi stack output edge_hostname"
pulumi.export("edge_hostname", edge_host.edge_hostname)
#pulumi.export("property_rules", property_rules)