# ==================================================================================================
# Copyright 2011 Twitter, Inc.
# --------------------------------------------------------------------------------------------------
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this work except in compliance with the License.
# You may obtain a copy of the License in the LICENSE file, or at:
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==================================================================================================

from collections import defaultdict

from twitter.common.collections import OrderedSet

from twitter.pants.base.build_manual import manual
from twitter.pants.base.target import AbstractTarget

from .exclude import Exclude
from .external_dependency import ExternalDependency


class Artifact(object):
  """
  Specification for an Ivy Artifact for this jar dependency.

  See: http://ant.apache.org/ivy/history/latest-milestone/ivyfile/artifact.html
  """

  _HASH_KEYS = (
    'name',
    'type_',
    'ext',
    'conf',
    'url',
    'classifier',
  )

  def __init__(self, name, type_=None, ext=None, conf=None, url=None, classifier=None):
    """
    :param name: The name of the published artifact. This name must not include revision.
    :param type_: The type of the published artifact. It's usually its extension, but not
      necessarily. For instance, ivy files are of type 'ivy' but have 'xml' extension.
    :param ext: The extension of the published artifact.
    :param conf: The public configuration in which this artifact is published. The '*' wildcard can
      be used to designate all public configurations.
    :param url: The url at which this artifact can be found if it isn't located at the standard
      location in the repository
    :param classifier: The maven classifier of this artifact.
    """
    self.name = name
    self.type_ = type_ or 'jar'
    self.ext = ext
    self.conf = conf
    self.url = url
    self.classifier = classifier

  def cache_key(self):
    return ''.join(str(getattr(self, key)) for key in self._HASH_KEYS)

  def __repr__(self):
    return ('Artifact(%r, type_=%r, ext=%r, conf=%r, url=%r, classifier=%r)'
            % (self.name, self.type_, self.ext, self.conf, self.url, self.classifier))



@manual.builddict(tags=["jvm"])
class JarDependency(ExternalDependency, AbstractTarget):
  """A pre-built Maven repository dependency."""

  _JAR_HASH_KEYS = (
    'org',
    'name',
    'rev',
    'force',
    'excludes',
    'transitive',
    'mutable',
  )

  def __init__(self, org, name, rev=None, force=False, ext=None, url=None, apidocs=None,
               type_=None, classifier=None, mutable=None, exclusives=None):
    """
    :param string org: The Maven ``groupId`` of this dependency.
    :param string name: The Maven ``artifactId`` of this dependency.
    :param string rev: The Maven ``version`` of this dependency.
      If unspecified the latest available version is used.
    :param boolean force: Force this specific artifact revision even if other transitive
      dependencies specify a different revision. This requires specifying the ``rev`` parameter.
    :param string ext: Extension of the artifact if different from the artifact type.
      This is sometimes needed for artifacts packaged with Maven bundle type but stored as jars.
    :param string url: URL of this artifact, if different from the Maven repo standard location
      (specifying this parameter is unusual).
    :param string apidocs: URL of existing javadocs, which if specified, pants-generated javadocs
      will properly hyperlink {\ @link}s.
    :param string type_: Artifact packaging type.
    :param string classifier: Classifier specifying the artifact variant to use.
      Use ``with_artifact`` to include multiple artifacts with different classifiers.
    :param boolean mutable: Inhibit caching of this mutable artifact. A common use is for
      Maven -SNAPSHOT style artifacts in an active development/integration cycle.
    """
    self.org = org
    self.name = name
    self.rev = rev
    self.force = force
    self.excludes = []
    self.transitive = True
    self.apidocs = apidocs
    self.mutable = mutable
    self._classifier = classifier

    self.artifacts = []
    if ext or url or type_ or classifier:
      self.with_artifact(name=name, type_=type_, ext=ext, url=url, classifier=classifier)

    self.id = "%s-%s-%s" % (self.org, self.name, self.rev)
    self._configurations = ['default']
    self.declared_exclusives = defaultdict(set)
    if exclusives is not None:
      for k in exclusives:
        self.declared_exclusives[k] |= exclusives[k]

    # Support legacy method names
    # TODO(John Sirois): introduce a deprecation cycle for these and then kill
    self.withSources = self.with_sources
    self.withDocs = self.with_docs

    self.declared_exclusives = defaultdict(set)
    if exclusives is not None:
      for k in exclusives:
        self.declared_exclusives[k] |= exclusives[k]

  @property
  def is_jar(self):
    return True

  @property
  def configurations(self):
    confs = OrderedSet(self._configurations)
    confs.update(artifact.conf for artifact in self.artifacts if artifact.conf)
    return list(confs)

  @property
  def classifier(self):
    """Returns the maven classifier for this jar dependency.

    If the classifier is ambiguous; ie: there was no classifier set in the constructor and the jar
    dependency has multiple attached artifacts, a :class:`ValueError` is raised.
    """
    if self._classifier or len(self.artifacts) == 0:
      return self._classifier
    elif len(self.artifacts) == 1:
      return self.artifacts[0].classifier
    else:
      raise ValueError('Cannot determine classifier. No explicit classifier is set and this jar '
                       'has more than 1 artifact: %s\n\t%s'
                       % (self, '\n\t'.join(map(str, self.artifacts))))

  @manual.builddict()
  def exclude(self, org, name=None):
    """Adds a transitive dependency of this jar to the exclude list."""

    self.excludes.append(Exclude(org, name))
    return self

  @manual.builddict()
  def intransitive(self):
    """Declares this Dependency intransitive, indicating only the jar for the dependency itself
    should be downloaded and placed on the classpath"""

    self.transitive = False
    return self

  @manual.builddict()
  def with_sources(self):
    """This requests the artifact have its source jar fetched.
    (This implies there *is* a source jar to fetch.) Used in contexts
    that can use source jars (as of 2013, just eclipse and idea goals)."""
    self._configurations.append('sources')
    return self

  def with_docs(self):
    """This requests the artifact have its javadoc jar fetched.
    (This implies there *is* a javadoc jar to fetch.) Used in contexts
    that can use source jars (as of 2014, just eclipse and idea goals)."""
    self._configurations.append('javadoc')
    return self

  # TODO: This is necessary duck-typing because in some places JarDependency is treated like
  # a Target, even though it doesn't extend Target. Probably best to fix that.
  def has_label(self, label):
    return False

  def with_artifact(self, name=None, type_=None, ext=None, url=None, configuration=None,
                    classifier=None):
    """Sets an alternative artifact to fetch or adds additional artifacts if called multiple times.
    """
    artifact = Artifact(name or self.name, type_=type_, ext=ext, url=url, conf=configuration,
                        classifier=classifier)
    self.artifacts.append(artifact)
    return self

  def __eq__(self, other):
    result = (isinstance(other, JarDependency)
              and self.org == other.org
              and self.name == other.name
              and self.rev == other.rev)
    return result

  def __hash__(self):
    return hash((self.org, self.name, self.rev))

  def __ne__(self, other):
    return not self.__eq__(other)

  def __repr__(self):
    return self.id

  def cache_key(self):
    key = ''.join(str(getattr(self, key)) for key in self._JAR_HASH_KEYS)
    key += ''.join(sorted(self._configurations))
    key += ''.join(a.cache_key() for a in sorted(self.artifacts, key=lambda a: a.name + a.type_))
    return key

  def resolve(self):
    yield self

  def walk(self, work, predicate=None):
    if not predicate or predicate(self):
      work(self)

  def _as_jar_dependencies(self):
    yield self
