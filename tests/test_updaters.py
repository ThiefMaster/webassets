import os
from webassets import Environment, Bundle
from webassets.updater import TimestampUpdater, BundleDefUpdater
from webassets.cache import MemoryCache
from helpers import BuildTestHelper


class TestBundleDefBaseUpdater:
    """Test the updater which caches bundle definitions to determine
    changes.
    """

    def setup(self):
        self.env = Environment(None, None)  # we won't create files
        self.env.cache = MemoryCache(capacity=100)
        self.bundle = Bundle(output="target")
        self.updater = BundleDefUpdater()

    def test_no_rebuild_required(self):
        # Fake an initial build
        self.updater.build_done(self.bundle, self.env)
        # without any changes, no rebuild is required
        assert self.updater.needs_rebuild(self.bundle, self.env) == False

        # Build of another bundle won't change that, i.e. we use the
        # correct caching key for each bundle.
        bundle2 = Bundle(output="target2")
        self.updater.build_done(bundle2, self.env)
        assert self.updater.needs_rebuild(self.bundle, self.env) == False

    def test_filters_changed(self):
        self.updater.build_done(self.bundle, self.env)
        self.bundle.filters += ('jsmin',)
        assert self.updater.needs_rebuild(self.bundle, self.env) == True

    def test_contents_changed(self):
        self.updater.build_done(self.bundle, self.env)
        self.bundle.contents += ('foo.css',)
        assert self.updater.needs_rebuild(self.bundle, self.env) == True

    def test_debug_changed(self):
        self.updater.build_done(self.bundle, self.env)
        self.bundle.debug = not self.bundle.debug
        assert self.updater.needs_rebuild(self.bundle, self.env) == True

    def test_depends_changed(self):
        # Changing the depends attribute of a bundle will NOT cause
        # a rebuild. This is a close call, and might just as well work
        # differently. I decided that the purity of the Bundle.__hash__
        # implementation in not including anything that isn't affecting
        # to the final output bytes was more important. If the user
        # is changing depends than after the next rebuild that change
        # will be effective anyway.
        self.updater.build_done(self.bundle, self.env)
        self.bundle.depends += ['foo']
        assert self.updater.needs_rebuild(self.bundle, self.env) == False


class TestTimestampUpdater(BuildTestHelper):

    default_files = {'in': '', 'out': ''}

    def setup(self):
        BuildTestHelper.setup(self)

        # Test the timestamp updater with cache disabled, so that the
        # BundleDefUpdater() base class won't interfere.
        self.m.cache = False
        self.m.versioner.updater = self.updater = TimestampUpdater()

    def test_default(self):
        bundle = self.mkbundle('in', output='out')

        # Set both times to the same timestamp
        now = self.setmtime('in', 'out')
        assert self.updater.needs_rebuild(bundle, self.m) == False

        # Make in file older than out file
        self.setmtime('in', mtime=now-100)
        self.setmtime('out', mtime=now)
        assert self.updater.needs_rebuild(bundle, self.m) == False

        # Make in file newer than out file
        self.setmtime('in', mtime=now)
        self.setmtime('out', mtime=now-100)
        assert self.updater.needs_rebuild(bundle, self.m) == True

    def test_bundle_definition_change(self):
        """Test that the timestamp updater uses the base class
        functionality of determining a bundle definition change as
        well.
        """
        self.m.cache = MemoryCache(capacity=100)
        bundle = self.mkbundle('in', output='out')

        # Fake an initial build
        self.updater.build_done(bundle, self.m)

        # Make in file older than out file
        now = self.setmtime('out')
        self.setmtime('in', mtime=now-100)
        assert self.updater.needs_rebuild(bundle, self.m) == False

        # Change the bundle definition
        bundle.filters = 'jsmin'

        # Timestamp updater will says we need to rebuild.
        assert self.updater.needs_rebuild(bundle, self.m) == True
        self.updater.build_done(bundle, self.m)

    def test_depends(self):
        """Test the timestamp updater properly considers additional
        bundle dependencies."""
        self.create_files({'d.sass': '', 'd.other': ''})
        bundle = self.mkbundle('in', output='out', depends=('*.sass',))

        # First, ensure that the dependency definition is not
        # unglobbed until we actually need to do it.
        internal_attr = '_resolved_depends'
        assert not getattr(bundle, internal_attr, None)

        # Make all files older than the output
        now = self.setmtime('out')
        self.setmtime('in', 'd.sass', 'd.other', mtime=now-100)
        assert self.updater.needs_rebuild(bundle, self.m) == False

        # Touch the file that is supposed to be unrelated
        now = self.setmtime('d.other', mtime=now+100)
        assert self.updater.needs_rebuild(bundle, self.m) == False

        # Touch the dependency file - now a rebuild is required
        now = self.setmtime('d.sass', mtime=now+100)
        assert self.updater.needs_rebuild(bundle, self.m) == True

        # Finally, counter-check that our previous check for the
        # internal attribute was valid.
        assert hasattr(bundle, internal_attr)
