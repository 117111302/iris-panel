"""
View functions to handler submission events
"""
from MySQLdb.constants.ER import DUP_ENTRY

from django.db import IntegrityError
from django.db.transaction import atomic
from django.contrib.auth.decorators import permission_required

from rest_framework.status import (
    HTTP_200_OK, HTTP_201_CREATED, HTTP_202_ACCEPTED,
    HTTP_406_NOT_ACCEPTABLE,
    )
from rest_framework.response import Response
from rest_framework.decorators import api_view

from iris.core.models import (
    Submission, SubmissionBuild, ImageBuild, PackageBuild,
    )
from iris.submissions.views.event_forms import (
    SubmittedForm, PreCreatedForm, PackageBuiltForm,
    ImageBuildingForm, ImageCreatedForm, RepaActionForm,
    )

# pylint: disable=C0111,E1101,W0703,W0232,E1002,R0903,C0103
# W0232: 25,0:SubmittedForm: Class has no __init__ method
# E1002: 78,4:PreCreatedForm.clean: Use of super on an old style class
# R0903: 90,0:ImageBuildingForm: Too few public methods (1/2)

PUBLISH_EVENTS_PERM = 'core.publish_events'

@atomic
@api_view(["POST"])
@permission_required(PUBLISH_EVENTS_PERM, raise_exception=True)
def events_handler(request):
    """
    Common event handler for all submissions events
    """
    handlers = {
        'submitted': submitted,
        'pre_created': pre_created,
        'package_built': package_built,
        'image_building': image_building,
        'image_created': image_created,
        'repa_action': repa_action,
        }
    typ = request.POST.get('event')
    handler = handlers.get(typ)
    if not handler:
        return Response({'detail': 'Unknown event type'},
                        status=HTTP_406_NOT_ACCEPTABLE)
    return handler(request)


def submitted(request):
    """
    Event that occurs when a tag submitted

    tag -- Tag name
    gittree -- Git tree path
    commit_id -- Commit hash
    submitter_email -- Email of submitter
    """
    form = SubmittedForm(request.POST)
    if not form.is_valid():
        return Response({'detail': form.errors.as_text()},
                        status=HTTP_406_NOT_ACCEPTABLE)
    data = form.cleaned_data

    sub = Submission(
        name=data['tag'],
        gittree=data['gitpath'],
        commit=data['commit_id'],
        owner=data['submitter_email'],
        status='SUBMITTED',
        )
    try:
        sub.save()
    except IntegrityError as err:
        if err.args[0] == DUP_ENTRY:
            return Response({'detail': str(err)}, status=HTTP_202_ACCEPTED)
        raise

    return Response({'detail': 'Tag submitted'}, status=HTTP_201_CREATED)


def pre_created(request):
    """
    Event that happens when a pre-release project had been created

    gitpath -- Git tree path
    tag -- Tag name
    product -- Target product name
    project -- Pre-release project name
    """
    form = PreCreatedForm(request.POST)
    if not form.is_valid():
        return Response({'detail': form.errors.as_text()},
                        status=HTTP_406_NOT_ACCEPTABLE)
    data = form.cleaned_data

    build = SubmissionBuild(
        submission=data['submission'],
        product=data['product'],
        group=data['project'])
    try:
        build.save()
    except IntegrityError as err:
        if err.args[0] == DUP_ENTRY:
            return Response({'detail': str(err)}, status=HTTP_202_ACCEPTED)
        raise
    return Response({'detail': 'Pre-release project created'},
                    status=HTTP_201_CREATED)


def package_built(request):
    """
    Event that happens when a package was built

    name -- Package name
    repo -- Building repository
    arch -- Building architecture
    project -- Pre-release project name
    status -- Status
    url -- Live repo URL
    log -- Building log URL
    """
    form = PackageBuiltForm(request.POST)
    if not form.is_valid():
        return Response({'detail': form.errors.as_text()},
                        status=HTTP_406_NOT_ACCEPTABLE)
    data = form.cleaned_data

    PackageBuild.objects.create(
        package=data['name'],
        status=data['status'],
        repo=data['repo'],
        arch=data['arch'],
        url=data['url'],
        log=data['log'],
        group=data['project'],
        )
    msg = {'detail': '%s bulit %s' % (data['name'], data['status'])}
    return Response(msg, status=HTTP_200_OK)


def image_building(request):
    """
    Event that happens when a image started to build

    name -- Image name
    project -- Pre-release project name
    """
    form = ImageBuildingForm(request.POST)
    if not form.is_valid():
        return Response({'detail': form.errors.as_text()},
                        status=HTTP_406_NOT_ACCEPTABLE)

    data = form.cleaned_data

    group = data['project']
    group.status = '20_IMGBUILDING'
    group.save()

    ibuild = ImageBuild(name=data['name'],
                        status='BUILDING',
                        group=group)
    ibuild.save()
    return Response({'detail': 'Image started to build'},
                    status=HTTP_200_OK)


def image_created(request):
    """
    Event that happends when a image created

    name -- Image name
    project -- Pre-release project name
    status -- status
    url -- Image URL
    """
    form = ImageCreatedForm(request.POST)
    if not form.is_valid():
        return Response({'detail': form.errors.as_text()},
                        status=HTTP_406_NOT_ACCEPTABLE)

    data = form.cleaned_data
    print data
    ok = data['status'] == 'success'

    group = data['project']
    if ok:
        group.status = '30_READY'
    else:
        group.status = '25_IMGFAILED'
    group.save()

    ibuild = data['name']
    ibuild.log = data['log']
    if ok:
        ibuild.url = data['url']
        ibuild.status = 'SUCCESS'
    else:
        ibuild.status = 'FAILURE'
    ibuild.save()
    return Response({'detail': 'Image created %s' % data['status']},
                    status=HTTP_200_OK)


def repa_action(request):
    """
    Event that happens when `repa` operates on some pre-release project

    project - Pre-release project
    status - Accepted or rejected
    who - Operator's Email
    reason - Explanation
    when - When this happened
    """
    form = RepaActionForm(request.POST)
    if not form.is_valid():
        return Response({'detail': form.errors.as_text()},
                        status=HTTP_406_NOT_ACCEPTABLE)
    data = form.cleaned_data
    group = data['project']
    group.status = data['status']
    group.operator = data['who']
    group.operator_on = data['when']
    group.save()
    return Response({'detail': 'Action %s received' % data['status']},
                    status=HTTP_200_OK)